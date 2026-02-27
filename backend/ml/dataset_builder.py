"""
QuantPulse – Dataset Builder (MySQL → ML Dataset)
===================================================
Construye dataset supervisado desde trades históricos en MySQL.

FLUJO:
  1. Query trades cerrados (PROFIT / LOSS)
  2. Join con trade_features
  3. Feature engineering adicional
  4. Encoding de categóricas
  5. Normalization
  6. Time-based split

PREVENCIÓN DE DATA LEAKAGE:
  - No se usan features del futuro (post-entrada).
  - Los splits respetan el orden temporal.
  - La normalización se calcula SOLO en train.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import TimeSeriesSplit

from backend.ml.config import MLConfig, default_config

logger = logging.getLogger("quantpulse.ml.dataset")


class DatasetBuilder:
    """
    Construye datasets para entrenamiento ML desde MySQL.
    
    RESPONSABILIDADES:
      - Extracción de datos vía Repository
      - Feature engineering
      - Encoding de categóricas
      - Normalización (sin data leakage)
      - Time-based splitting
    
    USO:
        builder = DatasetBuilder(config=MLConfig())
        X_train, X_test, y_train, y_test = await builder.build_dataset(session)
    """
    
    def __init__(self, config: MLConfig = None):
        self._config = config or default_config
        self._scaler: Optional[StandardScaler] = None
        self._label_encoders: Dict[str, LabelEncoder] = {}
        self._feature_stats: Dict[str, Dict[str, float]] = {}
    
    # ════════════════════════════════════════════════════════════════
    #  EXTRACCIÓN DE DATOS
    # ════════════════════════════════════════════════════════════════
    
    async def load_from_db(
        self,
        session,  # AsyncSession
        min_date: datetime = None,
        max_date: datetime = None,
        symbols: List[str] = None,
    ) -> pd.DataFrame:
        """
        Extrae trades cerrados con sus features desde MySQL.
        
        QUERY OPTIMIZADO:
        - JOIN trade_features ON trade_id
        - Filtro por status IN ('PROFIT', 'LOSS')
        - Ordenado por created_at ASC (crítico para split temporal)
        """
        from sqlalchemy import select, and_, or_
        from backend.app.infrastructure.models.trade import TradeModel
        from backend.app.infrastructure.models.trade_features import TradeFeatureModel
        from backend.app.infrastructure.models.symbol import SymbolModel
        
        # Base query
        query = (
            select(
                TradeModel,
                TradeFeatureModel,
                SymbolModel.name.label("symbol_name")
            )
            .join(TradeFeatureModel, TradeModel.id == TradeFeatureModel.trade_id)
            .join(SymbolModel, TradeModel.symbol_id == SymbolModel.id)
            .where(
                TradeModel.status.in_(["PROFIT", "LOSS"])
                if self._config.exclude_expired
                else TradeModel.status.in_(["PROFIT", "LOSS", "EXPIRED"])
            )
            .order_by(TradeModel.created_at.asc())  # Orden temporal
        )
        
        # Filtros opcionales
        if min_date:
            query = query.where(TradeModel.created_at >= min_date)
        if max_date:
            query = query.where(TradeModel.created_at <= max_date)
        if symbols:
            query = query.where(SymbolModel.name.in_(symbols))
        
        result = await session.execute(query)
        rows = result.all()
        
        if not rows:
            logger.warning("No se encontraron trades cerrados para entrenar")
            return pd.DataFrame()
        
        # Construir DataFrame
        records = []
        for trade, features, symbol in rows:
            record = {
                # Metadata
                "trade_id": trade.id,
                "symbol": symbol,
                "timeframe": trade.timeframe or "5s",
                "signal_type": trade.signal_type,  # BUY / SELL
                "created_at": trade.created_at,
                
                # Target
                "status": trade.status,
                "is_profit": 1 if trade.status == "PROFIT" else 0,
                
                # Trade metrics (para validación, NO como features)
                "actual_rr": float(trade.actual_rr or 0),
                "pnl_pct": float(trade.pnl_pct or 0),
                "duration_seconds": trade.duration_seconds,
                
                # Features de entrada (momento de la señal)
                "ema9": float(features.ema9 or 0),
                "ema21": float(features.ema21 or 0),
                "ema_distance": float(features.ema_distance or 0),
                "rsi_value": float(features.rsi14 or 50),
                "rsi_slope": float(features.rsi_divergence or 0),
                "atr_14": float(features.atr14 or 0),
                "volatility_20": float(features.volatility_ratio or 0),
                "candle_body_ratio": float(features.range_percentile or 0.5),
                "distance_to_support": float(features.sr_distance or 0),
                "distance_to_resistance": float(features.sr_distance or 0),
                "momentum_5": float(features.momentum_5 or 0),
                "momentum_10": float(features.momentum_10 or 0),
                "consolidation_score": float(features.consolidation_bars or 0),
                "volume_ratio": float(features.volume_ratio or 1.0),
                "rr_ratio": float(features.rsi_zone or 2.0),  # Planned RR
                "trend_strength": float(features.higher_tf_trend or 0),
                "primary_condition": features.conditions_met or "unknown",
            }
            records.append(record)
        
        df = pd.DataFrame(records)
        logger.info(
            "Dataset cargado: %d trades (%d PROFIT, %d LOSS) desde %s hasta %s",
            len(df),
            df["is_profit"].sum(),
            len(df) - df["is_profit"].sum(),
            df["created_at"].min().strftime("%Y-%m-%d") if len(df) > 0 else "N/A",
            df["created_at"].max().strftime("%Y-%m-%d") if len(df) > 0 else "N/A",
        )
        
        return df
    
    # ════════════════════════════════════════════════════════════════
    #  FEATURE ENGINEERING
    # ════════════════════════════════════════════════════════════════
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Feature engineering adicional.
        
        NUEVAS FEATURES CREADAS:
          - time_of_day: Hora del día (0-23)
          - day_of_week: Día de la semana (0-6)
          - ema_cross_strength: |ema_distance| normalizado
          - rsi_extreme: 1 si RSI < 30 o > 70
          - trend_alignment: 1 si EMA y RSI coinciden en dirección
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # Temporal features
        df["time_of_day"] = df["created_at"].dt.hour
        df["day_of_week"] = df["created_at"].dt.dayofweek
        
        # EMA features derivadas
        df["ema_cross_strength"] = np.abs(df["ema_distance"])
        df["ema_bullish"] = (df["ema_distance"] > 0).astype(int)
        
        # RSI features derivadas
        df["rsi_extreme"] = ((df["rsi_value"] < 30) | (df["rsi_value"] > 70)).astype(int)
        df["rsi_oversold"] = (df["rsi_value"] < 35).astype(int)
        df["rsi_overbought"] = (df["rsi_value"] > 65).astype(int)
        
        # Alineación de indicadores
        rsi_bullish = df["rsi_value"] < 50
        ema_bullish = df["ema_distance"] > 0
        df["trend_alignment"] = (rsi_bullish == ema_bullish).astype(int)
        
        # Volatility features
        df["high_volatility"] = (df["volatility_20"] > df["volatility_20"].median()).astype(int)
        
        # S/R proximity
        df["near_sr"] = (
            (np.abs(df["distance_to_support"]) < 0.005) |
            (np.abs(df["distance_to_resistance"]) < 0.005)
        ).astype(int)
        
        logger.debug("Features adicionales creadas: %d nuevas columnas", 10)
        
        return df
    
    # ════════════════════════════════════════════════════════════════
    #  ENCODING Y NORMALIZACIÓN
    # ════════════════════════════════════════════════════════════════
    
    def encode_categoricals(
        self,
        df: pd.DataFrame,
        fit: bool = True,
    ) -> pd.DataFrame:
        """
        One-hot encoding para features categóricas.
        
        IMPORTANTE:
          - fit=True: Aprende encoding en train.
          - fit=False: Aplica encoding aprendido (test/inference).
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        for col in self._config.categorical_features:
            if col not in df.columns:
                continue
            
            if fit:
                self._label_encoders[col] = LabelEncoder()
                df[f"{col}_encoded"] = self._label_encoders[col].fit_transform(
                    df[col].fillna("unknown").astype(str)
                )
            else:
                if col in self._label_encoders:
                    # Handle unseen categories
                    known = set(self._label_encoders[col].classes_)
                    df[col] = df[col].fillna("unknown").astype(str)
                    df[col] = df[col].apply(lambda x: x if x in known else "unknown")
                    df[f"{col}_encoded"] = self._label_encoders[col].transform(df[col])
        
        # One-hot para signal_type (siempre necesario)
        if "signal_type" in df.columns:
            df["is_buy"] = (df["signal_type"] == "BUY").astype(int)
            df["is_sell"] = (df["signal_type"] == "SELL").astype(int)
        
        return df
    
    def normalize_features(
        self,
        df: pd.DataFrame,
        feature_columns: List[str],
        fit: bool = True,
    ) -> pd.DataFrame:
        """
        Z-score normalization para features numéricas.
        
        PREVENCIÓN DE DATA LEAKAGE:
          - fit=True: Calcula mean/std en train SOLAMENTE.
          - fit=False: Usa mean/std calculados en train.
        """
        if df.empty or not feature_columns:
            return df
        
        df = df.copy()
        available = [c for c in feature_columns if c in df.columns]
        
        if not available:
            return df
        
        if fit:
            self._scaler = StandardScaler()
            
            # Guardar stats para diagnóstico
            for col in available:
                self._feature_stats[col] = {
                    "mean": df[col].mean(),
                    "std": df[col].std(),
                    "min": df[col].min(),
                    "max": df[col].max(),
                }
            
            df[available] = self._scaler.fit_transform(df[available].fillna(0))
            logger.debug("Scaler fitted en %d features", len(available))
        else:
            if self._scaler is None:
                raise ValueError("Scaler no entrenado. Llama con fit=True primero.")
            df[available] = self._scaler.transform(df[available].fillna(0))
        
        # Clip outliers si está configurado
        if self._config.handle_outliers:
            for col in available:
                df[col] = df[col].clip(-3, 3)  # ±3 std
        
        return df
    
    # ════════════════════════════════════════════════════════════════
    #  TIME-BASED SPLITTING
    # ════════════════════════════════════════════════════════════════
    
    def time_split(
        self,
        df: pd.DataFrame,
        test_size: float = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split temporal: Train con datos antiguos, Test con recientes.
        
        POR QUÉ ES CRÍTICO:
          Un split aleatorio causa data leakage porque el modelo
          "ve" patrones del futuro durante training.
          
          En trading real, SIEMPRE entrenamos con datos pasados
          y predecimos el futuro.
        
        EJEMPLO:
          Datos: Ene-Jun
          Train: Ene-May (80%)
          Test: Jun (20%)
        """
        if df.empty:
            return df, df
        
        test_size = test_size or self._config.test_size
        
        # Asegurar orden temporal
        df = df.sort_values("created_at").reset_index(drop=True)
        
        split_idx = int(len(df) * (1 - test_size))
        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx:].copy()
        
        logger.info(
            "Time split: Train=%d (hasta %s), Test=%d (desde %s)",
            len(train_df),
            train_df["created_at"].max().strftime("%Y-%m-%d %H:%M"),
            len(test_df),
            test_df["created_at"].min().strftime("%Y-%m-%d %H:%M"),
        )
        
        return train_df, test_df
    
    def get_walk_forward_splits(
        self,
        df: pd.DataFrame,
        n_splits: int = None,
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Walk-forward (rolling window) cross-validation.
        
        PROCESO:
          Fold 1: Train[0:20%],   Test[20:40%]
          Fold 2: Train[0:40%],   Test[40:60%]
          Fold 3: Train[0:60%],   Test[60:80%]
          Fold 4: Train[0:80%],   Test[80:100%]
        
        VENTAJAS:
          - Simula backtesting real.
          - Evalúa estabilidad del modelo en diferentes períodos.
          - Detecta regime changes.
        """
        n_splits = n_splits or self._config.n_splits
        
        tscv = TimeSeriesSplit(n_splits=n_splits)
        splits = list(tscv.split(df))
        
        logger.info("Walk-forward: %d folds generados", len(splits))
        
        return splits
    
    # ════════════════════════════════════════════════════════════════
    #  PIPELINE COMPLETO
    # ════════════════════════════════════════════════════════════════
    
    async def build_dataset(
        self,
        session,  # AsyncSession
        min_date: datetime = None,
        max_date: datetime = None,
        symbols: List[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
        """
        Pipeline completo: MySQL → Dataset listo para ML.
        
        FLUJO:
          1. Cargar datos de MySQL
          2. Feature engineering
          3. Encoding categóricas
          4. Time split (train/test)
          5. Normalización (fit en train, transform en test)
        
        Returns:
            X_train, X_test, y_train, y_test, feature_names
        """
        # 1. Cargar datos
        df = await self.load_from_db(session, min_date, max_date, symbols)
        
        if len(df) < self._config.min_train_samples:
            raise ValueError(
                f"Dataset muy pequeño ({len(df)} trades). "
                f"Mínimo requerido: {self._config.min_train_samples}"
            )
        
        # 2. Feature engineering
        df = self.engineer_features(df)
        
        # 3. Encoding
        df = self.encode_categoricals(df, fit=True)
        
        # 4. Time split
        train_df, test_df = self.time_split(df)
        
        # 5. Features a usar
        numeric_features = self._config.get_all_features()
        derived_features = [
            "time_of_day", "day_of_week", "ema_cross_strength",
            "rsi_extreme", "trend_alignment", "high_volatility",
            "near_sr", "is_buy", "is_sell",
        ]
        feature_columns = [
            c for c in numeric_features + derived_features
            if c in train_df.columns
        ]
        
        # Agregar encoded categóricas
        for cat in self._config.categorical_features:
            if f"{cat}_encoded" in train_df.columns:
                feature_columns.append(f"{cat}_encoded")
        
        # 6. Normalización (fit en train SOLAMENTE)
        train_df = self.normalize_features(train_df, feature_columns, fit=True)
        test_df = self.normalize_features(test_df, feature_columns, fit=False)
        
        # Aplicar encoding al test con encoders del train
        test_df = self.encode_categoricals(test_df, fit=False)
        
        # 7. Extraer arrays
        X_train = train_df[feature_columns].values
        X_test = test_df[feature_columns].values
        y_train = train_df["is_profit"].values
        y_test = test_df["is_profit"].values
        
        logger.info(
            "Dataset listo: X_train=%s, X_test=%s, Features=%d",
            X_train.shape, X_test.shape, len(feature_columns),
        )
        
        return X_train, X_test, y_train, y_test, feature_columns
    
    def get_feature_stats(self) -> Dict[str, Dict[str, float]]:
        """Retorna estadísticas de features (mean, std, min, max)."""
        return self._feature_stats
    
    def get_scaler(self) -> Optional[StandardScaler]:
        """Retorna el scaler entrenado para persistencia."""
        return self._scaler
    
    def set_scaler(self, scaler: StandardScaler):
        """Carga un scaler previamente entrenado."""
        self._scaler = scaler
