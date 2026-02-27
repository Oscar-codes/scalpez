"""
QuantPulse – ML Bounded Context
=================================
Machine Learning como contexto acotado dentro de infrastructure.

Estructura:
- training/: Entrenamiento de modelos
- inference/: Predicción en producción
- registry/: Versionado de modelos
- config.py: Configuración ML

DESACOPLAMIENTO:
Este bounded context implementa IMLPredictor de application/ports.
El resto del sistema NO conoce detalles de ML (XGBoost, features, etc.)
"""

from backend.infrastructure.ml.config import MLConfig

__all__ = ["MLConfig"]
