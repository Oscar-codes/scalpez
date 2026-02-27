"""
QuantPulse – Machine Learning Module
=====================================
Sistema ML profesional para mejorar el edge estadístico en trading.

ARQUITECTURA:
  - dataset_builder: Extrae y preprocesa datos de MySQL.
  - model_trainer: Entrena modelos con validación temporal.
  - model_inference: Predicciones en tiempo real.
  - model_registry: Versionado y gestión de modelos.

MODELOS SOPORTADOS:
  - XGBoost (default): Óptimo para datos tabulares financieros.
  - LightGBM: Alternativa más rápida para grandes datasets.
  - RandomForest: Baseline robusto.
  - LogisticRegression: Benchmark lineal.

PREVENCIÓN DE ERRORES:
  - Time-based split: Evita data leakage temporal.
  - Walk-forward validation: Simula condiciones reales.
  - Feature normalization: Estabilidad numérica.
  - Early stopping: Previene sobreajuste.
"""

from backend.ml.dataset_builder import DatasetBuilder
from backend.ml.model_trainer import ModelTrainer
from backend.ml.model_inference import ModelInference
from backend.ml.model_registry import ModelRegistry
from backend.ml.config import MLConfig

__all__ = [
    "DatasetBuilder",
    "ModelTrainer",
    "ModelInference",
    "ModelRegistry",
    "MLConfig",
]
