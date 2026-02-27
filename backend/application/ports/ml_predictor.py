"""
QuantPulse – Application Port: ML Predictor
=============================================
Interfaz para predicción de Machine Learning.

Los use cases solicitan predicciones; la infraestructura
decide QUÉ modelo usar y CÓMO hacerlo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class PredictionResult:
    """Resultado de una predicción ML."""
    
    probability: float          # P(PROFIT) ∈ [0, 1]
    should_emit: bool           # True si probability >= threshold
    threshold: float            # Umbral usado
    model_version: str          # Versión del modelo
    features_used: Dict[str, float] = None  # Features extraídas
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "probability": round(self.probability, 4),
            "should_emit": self.should_emit,
            "threshold": self.threshold,
            "model_version": self.model_version,
            "features_used": self.features_used,
        }


class IMLPredictor(ABC):
    """
    Interfaz para predicción ML.
    
    IMPLEMENTACIONES POSIBLES:
    - XGBoostPredictor (producción)
    - RandomForestPredictor (alternativa)
    - MockPredictor (testing)
    - NoOpPredictor (ML desactivado)
    """
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Verifica si el predictor está disponible.
        
        Returns:
            True si hay modelo cargado y funcionando
        """
        pass
    
    @abstractmethod
    async def predict(
        self,
        features: Dict[str, Any],
        threshold: float = 0.55,
    ) -> PredictionResult:
        """
        Realiza predicción de P(PROFIT).
        
        Args:
            features: Dict con features de la señal
            threshold: Umbral mínimo para emitir
        
        Returns:
            PredictionResult con probabilidad y decisión
        """
        pass
    
    @abstractmethod
    async def extract_features(
        self,
        signal_data: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Extrae features numéricas para el modelo.
        
        Args:
            signal_data: Datos de la señal
            market_data: Datos de mercado (indicadores, precios)
        
        Returns:
            Dict con features normalizadas
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Obtiene información del modelo activo.
        
        Returns:
            Dict con versión, métricas de training, etc.
        """
        pass
    
    @abstractmethod
    async def reload_model(self, version: str = None) -> bool:
        """
        Recarga el modelo (hot-reload).
        
        Args:
            version: Versión específica, o None para última
        
        Returns:
            True si recarga exitosa
        """
        pass
