"""
Model Inference Adapter.

Adaptador del ModelInference existente para la nueva arquitectura.
Implementa IMLPredictor para integrarse con Clean Architecture.
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from backend.application.ports.ml_predictor import IMLPredictor, PredictionResult
from backend.shared.config.settings import Settings

# Re-export del ModelInference original para compatibilidad
try:
    from backend.ml.model_inference import ModelInference as LegacyModelInference
    from backend.ml.model_inference import InferenceResult
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    LegacyModelInference = None
    InferenceResult = None


class ModelInference(IMLPredictor):
    """
    Implementación de IMLPredictor usando el ModelInference legacy.
    
    Actúa como adaptador entre el sistema ML existente y la nueva arquitectura.
    """
    
    def __init__(self, settings: Settings):
        self._settings = settings
        # Usar Any para evitar error de tipo con importación condicional
        self._legacy_inference: Optional[Any] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Inicializa el modelo ML."""
        if not _ML_AVAILABLE:
            raise RuntimeError("ML module not available")
        
        if self._initialized:
            return
        
        from backend.ml.config import MLConfig
        
        config = MLConfig(
            min_threshold=self._settings.ml_threshold,
            models_dir=self._settings.ml_models_dir,
        )
        
        self._legacy_inference = LegacyModelInference(config)
        self._initialized = True
    
    async def predict(
        self,
        symbol: str,
        features: Dict[str, Any],
    ) -> PredictionResult:
        """
        Realiza predicción ML.
        
        Args:
            symbol: Símbolo del activo
            features: Features para la predicción
        
        Returns:
            PredictionResult con probabilidad y decisión
        """
        if not self._initialized or self._legacy_inference is None:
            await self.initialize()
        
        if self._legacy_inference is None:
            return PredictionResult(
                confidence=0.5,
                should_trade=True,
                model_version="unavailable",
            )
        
        # Extraer features en el formato esperado por el modelo legacy
        try:
            result = self._legacy_inference.predict(
                symbol=symbol,
                indicators=features,
            )
            
            return PredictionResult(
                confidence=result.probability,
                should_trade=result.should_emit,
                model_version=result.model_version,
                metadata={
                    "threshold": result.threshold,
                    "features_used": result.features_used,
                },
            )
        except Exception as e:
            # Si hay error, permitir el trade pero registrar
            import logging
            logger = logging.getLogger("quantpulse.ml.inference")
            logger.warning(f"ML prediction error: {e}")
            
            return PredictionResult(
                confidence=0.5,
                should_trade=True,
                model_version="error",
                metadata={"error": str(e)},
            )
    
    def is_available(self) -> bool:
        """Verifica si el módulo ML está disponible."""
        return _ML_AVAILABLE and self._initialized
    
    async def close(self) -> None:
        """Libera recursos."""
        self._legacy_inference = None
        self._initialized = False


# Re-export para compatibilidad
__all__ = [
    "ModelInference",
    "LegacyModelInference",
    "InferenceResult",
    "PredictionResult",
]
