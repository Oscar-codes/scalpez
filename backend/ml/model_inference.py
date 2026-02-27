"""
QuantPulse – Model Inference (Predicción en Tiempo Real)
==========================================================
Inferencia de probabilidad de éxito para señales en tiempo real.

INTEGRACIÓN CON SIGNAL ENGINE:
  1. Signal Engine detecta condiciones → genera Signal candidata
  2. Inference extrae features del contexto actual
  3. Modelo predice P(PROFIT)
  4. Si P >= threshold → emitir señal
  5. Si P < threshold → descartar silenciosamente

LATENCIA:
  Predicción individual: <1ms (modelo en memoria)
  No bloquea el event loop (numpy es CPU-bound pero rápido)

THREAD-SAFETY:
  El modelo sklearn/xgb es thread-safe para predict()
  No se reentrena durante inferencia
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import pickle
import json

import numpy as np

from backend.ml.config import MLConfig, default_config

logger = logging.getLogger("quantpulse.ml.inference")


class InferenceResult:
    """Resultado de una predicción."""
    
    def __init__(
        self,
        probability: float,
        threshold: float,
        should_emit: bool,
        features_used: Dict[str, float],
        model_version: str,
    ):
        self.probability = probability
        self.threshold = threshold
        self.should_emit = should_emit
        self.features_used = features_used
        self.model_version = model_version
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario."""
        return {
            "probability": round(self.probability, 4),
            "threshold": self.threshold,
            "should_emit": self.should_emit,
            "model_version": self.model_version,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def __repr__(self) -> str:
        return (
            f"InferenceResult(P={self.probability:.2%}, "
            f"thresh={self.threshold:.2f}, emit={self.should_emit})"
        )


class ModelInference:
    """
    Inferencia ML en tiempo real para filtrar señales.
    
    RESPONSABILIDADES:
      - Cargar modelo y scaler desde disco
      - Extraer features del contexto
      - Normalizar features (con scaler del training)
      - Predecir probabilidad
      - Aplicar threshold configurable
    
    USO:
        inference = ModelInference(config)
        inference.load_model("v1.0.0")  # Cargar desde disco
        
        # Por cada señal candidata:
        result = inference.predict(features_dict)
        if result.should_emit:
            # Emitir señal
    """
    
    def __init__(self, config: MLConfig = None):
        self._config = config or default_config
        self._model = None
        self._scaler = None
        self._feature_names: List[str] = []
        self._threshold: float = self._config.default_threshold
        self._model_version: str = "none"
        self._is_ready = False
        
        # Stats de inferencia
        self._total_predictions = 0
        self._total_emitted = 0
        self._total_filtered = 0
        self._avg_probability = 0.0
    
    # ════════════════════════════════════════════════════════════════
    #  CARGA DE MODELO
    # ════════════════════════════════════════════════════════════════
    
    def load_model(
        self,
        version: str = "latest",
        models_dir: Path = None,
    ) -> bool:
        """
        Carga modelo y scaler desde disco.
        
        ARCHIVOS ESPERADOS:
          models_dir/
            {version}/
              model.pkl       # Modelo entrenado
              scaler.pkl      # StandardScaler
              metadata.json   # Config, threshold, features
        
        Args:
            version: Versión a cargar ("latest" busca la más reciente)
            models_dir: Directorio de modelos
        
        Returns:
            True si carga exitosa
        """
        models_dir = models_dir or self._config.models_dir
        
        try:
            # Resolver "latest"
            if version == "latest":
                version = self._find_latest_version(models_dir)
                if not version:
                    logger.warning("No hay modelos disponibles")
                    return False
            
            model_path = models_dir / version
            
            if not model_path.exists():
                logger.error("Versión no encontrada: %s", model_path)
                return False
            
            # Cargar modelo
            with open(model_path / "model.pkl", "rb") as f:
                self._model = pickle.load(f)
            
            # Cargar scaler
            scaler_path = model_path / "scaler.pkl"
            if scaler_path.exists():
                with open(scaler_path, "rb") as f:
                    self._scaler = pickle.load(f)
            
            # Cargar metadata
            meta_path = model_path / "metadata.json"
            if meta_path.exists():
                with open(meta_path, "r") as f:
                    metadata = json.load(f)
                    self._threshold = metadata.get("threshold", self._config.default_threshold)
                    self._feature_names = metadata.get("feature_names", [])
            
            self._model_version = version
            self._is_ready = True
            
            logger.info(
                "Modelo cargado: %s (threshold=%.2f, features=%d)",
                version, self._threshold, len(self._feature_names),
            )
            
            return True
            
        except Exception as e:
            logger.error("Error cargando modelo: %s", e)
            return False
    
    def _find_latest_version(self, models_dir: Path) -> Optional[str]:
        """Encuentra la versión más reciente por timestamp."""
        if not models_dir.exists():
            return None
        
        versions = [
            d.name for d in models_dir.iterdir()
            if d.is_dir() and (d / "model.pkl").exists()
        ]
        
        if not versions:
            return None
        
        # Ordenar por timestamp en nombre (v1.0.0_20240227...)
        # o simplemente la más reciente por fecha de modificación
        versions.sort(
            key=lambda v: (models_dir / v).stat().st_mtime,
            reverse=True,
        )
        
        return versions[0]
    
    def set_model(
        self,
        model: Any,
        scaler: Any = None,
        feature_names: List[str] = None,
        threshold: float = None,
        version: str = "runtime",
    ):
        """
        Carga modelo directamente (sin disco).
        Útil para testing o cuando el modelo viene del trainer.
        """
        self._model = model
        self._scaler = scaler
        self._feature_names = feature_names or []
        self._threshold = threshold or self._config.default_threshold
        self._model_version = version
        self._is_ready = True
        
        logger.info("Modelo configurado: %s", version)
    
    # ════════════════════════════════════════════════════════════════
    #  EXTRACCIÓN DE FEATURES
    # ════════════════════════════════════════════════════════════════
    
    def extract_features(
        self,
        candle: Any,  # Candle entity
        indicators: Dict[str, float],
        sr_context: Dict[str, Any],
        signal_type: str,  # "BUY" / "SELL"
        planned_rr: float = 2.0,
    ) -> Dict[str, float]:
        """
        Extrae features del contexto actual para inferencia.
        
        FEATURES EXTRAÍDAS:
          - Indicadores: EMA, RSI, ATR
          - Volatilidad: calculada desde indicadores
          - S/R: distancia a niveles
          - Candlestick: body ratio, range
          - Temporal: hora, día
        
        NOTA: Esta función debe ser llamada en el momento
        de evaluar la señal, con datos ACTUALES.
        """
        features = {}
        
        # ── Indicadores ─────────────────────────────────────────
        ema9 = indicators.get("ema9", 0)
        ema21 = indicators.get("ema21", 0)
        rsi = indicators.get("rsi14", 50)
        rsi_prev = indicators.get("rsi14_prev", rsi)
        
        price = candle.close if hasattr(candle, "close") else 0
        
        features["ema9"] = ema9
        features["ema21"] = ema21
        features["ema_distance"] = (ema9 - ema21) / price if price > 0 else 0
        features["rsi_value"] = rsi
        features["rsi_slope"] = rsi - rsi_prev
        
        # ── Volatilidad ─────────────────────────────────────────
        atr = indicators.get("atr14", 0)
        avg_range = indicators.get("avg_range", 1)
        
        features["atr_14"] = atr
        features["volatility_20"] = atr / price if price > 0 else 0
        
        # ── Candlestick ─────────────────────────────────────────
        if hasattr(candle, "open"):
            body = abs(candle.close - candle.open)
            total_range = candle.high - candle.low if candle.high > candle.low else 1
            features["candle_body_ratio"] = body / total_range
        else:
            features["candle_body_ratio"] = 0.5
        
        # ── S/R ─────────────────────────────────────────────────
        support = sr_context.get("nearest_support", price)
        resistance = sr_context.get("nearest_resistance", price)
        
        features["distance_to_support"] = (price - support) / price if price > 0 else 0
        features["distance_to_resistance"] = (resistance - price) / price if price > 0 else 0
        
        # ── Momentum ───────────────────────────────────────────
        features["momentum_5"] = indicators.get("momentum_5", 0)
        features["momentum_10"] = indicators.get("momentum_10", 0)
        
        # ── Trading ────────────────────────────────────────────
        features["rr_ratio"] = planned_rr
        
        # ── Temporal ───────────────────────────────────────────
        now = datetime.utcnow()
        features["time_of_day"] = now.hour
        features["day_of_week"] = now.weekday()
        
        # ── Derivadas ──────────────────────────────────────────
        features["ema_cross_strength"] = abs(features["ema_distance"])
        features["rsi_extreme"] = 1 if rsi < 30 or rsi > 70 else 0
        features["rsi_oversold"] = 1 if rsi < 35 else 0
        features["rsi_overbought"] = 1 if rsi > 65 else 0
        
        # Alineación
        rsi_bullish = rsi < 50
        ema_bullish = features["ema_distance"] > 0
        features["trend_alignment"] = 1 if rsi_bullish == ema_bullish else 0
        
        # Volatilidad alta
        features["high_volatility"] = 1 if features["volatility_20"] > 0.001 else 0
        
        # Cerca de S/R
        features["near_sr"] = 1 if (
            abs(features["distance_to_support"]) < 0.005 or
            abs(features["distance_to_resistance"]) < 0.005
        ) else 0
        
        # Signal type encoding
        features["is_buy"] = 1 if signal_type == "BUY" else 0
        features["is_sell"] = 1 if signal_type == "SELL" else 0
        
        # Consolidation y trend (si disponibles)
        features["consolidation_score"] = sr_context.get("consolidation_bars", 0)
        features["trend_strength"] = indicators.get("trend_strength", 0)
        
        return features
    
    # ════════════════════════════════════════════════════════════════
    #  PREDICCIÓN
    # ════════════════════════════════════════════════════════════════
    
    def predict(
        self,
        features: Dict[str, float],
        threshold: float = None,
    ) -> InferenceResult:
        """
        Predice probabilidad de éxito para una señal.
        
        PROCESO:
          1. Ordenar features según feature_names del training
          2. Normalizar con scaler
          3. Predecir con modelo
          4. Aplicar threshold
        
        Args:
            features: Diccionario de features (de extract_features)
            threshold: Override del threshold (None = usar default)
        
        Returns:
            InferenceResult con probabilidad y decisión
        """
        threshold = threshold or self._threshold
        
        if not self._is_ready:
            # Modelo no cargado → emitir todas las señales
            logger.warning("Modelo no cargado, emitiendo señal sin filtro")
            return InferenceResult(
                probability=1.0,
                threshold=threshold,
                should_emit=True,
                features_used=features,
                model_version="none",
            )
        
        try:
            # Construir feature vector en orden correcto
            feature_vector = self._build_feature_vector(features)
            
            # Normalizar si hay scaler
            if self._scaler is not None:
                feature_vector = self._scaler.transform(
                    feature_vector.reshape(1, -1)
                )[0]
            
            # Predecir
            X = feature_vector.reshape(1, -1)
            probability = self._model.predict_proba(X)[0, 1]
            
            # Decisión
            should_emit = probability >= threshold
            
            # Stats
            self._total_predictions += 1
            if should_emit:
                self._total_emitted += 1
            else:
                self._total_filtered += 1
            
            # Running average
            self._avg_probability = (
                (self._avg_probability * (self._total_predictions - 1) + probability)
                / self._total_predictions
            )
            
            result = InferenceResult(
                probability=float(probability),
                threshold=threshold,
                should_emit=should_emit,
                features_used=features,
                model_version=self._model_version,
            )
            
            if not should_emit:
                logger.debug(
                    "Señal filtrada: P=%.2f%% < thresh=%.0f%% (version=%s)",
                    probability * 100,
                    threshold * 100,
                    self._model_version,
                )
            
            return result
            
        except Exception as e:
            logger.error("Error en predicción: %s", e)
            # En caso de error → emitir (fail-safe)
            return InferenceResult(
                probability=1.0,
                threshold=threshold,
                should_emit=True,
                features_used=features,
                model_version=self._model_version,
            )
    
    def _build_feature_vector(
        self,
        features: Dict[str, float],
    ) -> np.ndarray:
        """
        Construye vector de features en el orden esperado por el modelo.
        
        IMPORTANTE:
          Las features deben estar en el MISMO ORDEN que durante training.
          Features faltantes se rellenan con 0.
        """
        if not self._feature_names:
            # Sin metadata → usar todas las features en orden del dict
            return np.array(list(features.values()))
        
        vector = []
        for name in self._feature_names:
            value = features.get(name, 0)
            vector.append(float(value) if value is not None else 0.0)
        
        return np.array(vector)
    
    def predict_batch(
        self,
        features_list: List[Dict[str, float]],
        threshold: float = None,
    ) -> List[InferenceResult]:
        """
        Predicción en batch (más eficiente para múltiples señales).
        """
        return [self.predict(f, threshold) for f in features_list]
    
    # ════════════════════════════════════════════════════════════════
    #  THRESHOLD DINÁMICO
    # ════════════════════════════════════════════════════════════════
    
    def adjust_threshold(
        self,
        recent_win_rate: float,
        target_win_rate: float = 0.55,
    ):
        """
        Ajusta threshold dinámicamente basado en rendimiento reciente.
        
        LÓGICA:
          - Si win_rate < target → subir threshold (ser más selectivo)
          - Si win_rate > target + margen → bajar threshold (más señales)
        
        LÍMITES:
          - Mínimo: config.min_threshold (0.50)
          - Máximo: config.max_threshold (0.75)
        """
        if not self._config.dynamic_threshold:
            return
        
        margin = 0.05  # 5% de margen
        step = 0.02    # Ajustar en pasos de 2%
        
        old_threshold = self._threshold
        
        if recent_win_rate < target_win_rate - margin:
            # Subir threshold
            self._threshold = min(
                self._threshold + step,
                self._config.max_threshold,
            )
        elif recent_win_rate > target_win_rate + margin:
            # Bajar threshold
            self._threshold = max(
                self._threshold - step,
                self._config.min_threshold,
            )
        
        if self._threshold != old_threshold:
            logger.info(
                "Threshold ajustado: %.2f → %.2f (WR reciente=%.2f%%)",
                old_threshold,
                self._threshold,
                recent_win_rate * 100,
            )
    
    def set_threshold(self, threshold: float):
        """Establece threshold manualmente."""
        self._threshold = max(
            self._config.min_threshold,
            min(threshold, self._config.max_threshold),
        )
        logger.info("Threshold establecido: %.2f", self._threshold)
    
    # ════════════════════════════════════════════════════════════════
    #  ESTADÍSTICAS
    # ════════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de inferencia."""
        return {
            "total_predictions": self._total_predictions,
            "total_emitted": self._total_emitted,
            "total_filtered": self._total_filtered,
            "filter_rate": (
                self._total_filtered / self._total_predictions
                if self._total_predictions > 0 else 0
            ),
            "avg_probability": self._avg_probability,
            "current_threshold": self._threshold,
            "model_version": self._model_version,
            "is_ready": self._is_ready,
        }
    
    def reset_stats(self):
        """Resetea estadísticas (útil después de reentrenamiento)."""
        self._total_predictions = 0
        self._total_emitted = 0
        self._total_filtered = 0
        self._avg_probability = 0.0
    
    # ════════════════════════════════════════════════════════════════
    #  PROPIEDADES
    # ════════════════════════════════════════════════════════════════
    
    @property
    def is_ready(self) -> bool:
        """True si el modelo está cargado y listo."""
        return self._is_ready
    
    @property
    def threshold(self) -> float:
        """Threshold actual."""
        return self._threshold
    
    @property
    def model_version(self) -> str:
        """Versión del modelo cargado."""
        return self._model_version
