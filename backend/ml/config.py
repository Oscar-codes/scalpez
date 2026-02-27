"""
QuantPulse – ML Configuration
==============================
Configuración centralizada para el módulo de Machine Learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum


class ModelType(str, Enum):
    """Tipos de modelo soportados."""
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    RANDOM_FOREST = "random_forest"
    LOGISTIC = "logistic_regression"


class ValidationStrategy(str, Enum):
    """Estrategias de validación temporal."""
    TIME_SPLIT = "time_split"           # Train antiguo, test reciente
    WALK_FORWARD = "walk_forward"        # Rolling window
    EXPANDING = "expanding"              # Expanding window


@dataclass
class MLConfig:
    """
    Configuración completa del sistema ML.
    
    NOTAS DE DISEÑO:
    - Todos los parámetros tienen defaults razonables.
    - Los thresholds son conservadores para producción.
    - Walk-forward con 5 folds es el estándar para backtesting.
    """
    
    # ─── Rutas ──────────────────────────────────────────────────────
    models_dir: Path = field(default_factory=lambda: Path("backend/ml/models"))
    logs_dir: Path = field(default_factory=lambda: Path("backend/ml/logs"))
    
    # ─── Modelo ─────────────────────────────────────────────────────
    model_type: ModelType = ModelType.XGBOOST
    
    # ─── Features ───────────────────────────────────────────────────
    # Features núcleo siempre usadas
    core_features: List[str] = field(default_factory=lambda: [
        "ema_distance",          # (ema9 - ema21) / price
        "rsi_value",             # RSI 14
        "rsi_slope",             # RSI actual - RSI anterior
        "volatility_20",         # Volatilidad 20 períodos (std/mean)
        "candle_body_ratio",     # |close - open| / (high - low)
        "distance_to_support",   # (price - support) / price
        "distance_to_resistance",# (resistance - price) / price
        "rr_ratio",              # Risk-Reward ratio planificado
    ])
    
    # Features adicionales (opcional)
    extended_features: List[str] = field(default_factory=lambda: [
        "atr_14",               # Average True Range
        "momentum_5",           # ROC 5 períodos
        "momentum_10",          # ROC 10 períodos
        "volume_ratio",         # Volume / avg volume
        "time_of_day",          # Hora del día (0-23)
        "day_of_week",          # Día de la semana (0-6)
        "consolidation_score",  # Puntaje de consolidación
        "trend_strength",       # Fuerza de tendencia (ADX-like)
    ])
    
    # Features categóricas (one-hot encoding)
    categorical_features: List[str] = field(default_factory=lambda: [
        "symbol",               # Símbolo del instrumento
        "timeframe",            # Timeframe activo
        "signal_type",          # BUY / SELL
        "primary_condition",    # Condición principal de entrada
    ])
    
    # ─── Target ─────────────────────────────────────────────────────
    target_column: str = "is_profit"   # 1 = PROFIT, 0 = LOSS
    exclude_expired: bool = True        # Excluir trades EXPIRED del training
    
    # ─── Validación Temporal ────────────────────────────────────────
    validation_strategy: ValidationStrategy = ValidationStrategy.WALK_FORWARD
    test_size: float = 0.2              # 20% para test final
    n_splits: int = 5                   # Folds para walk-forward
    min_train_samples: int = 100        # Mínimo de samples para entrenar
    
    # ─── XGBoost Hyperparameters ────────────────────────────────────
    xgb_params: Dict[str, Any] = field(default_factory=lambda: {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "max_depth": 4,                 # Conservador para evitar overfit
        "learning_rate": 0.05,          # Lento pero estable
        "n_estimators": 300,
        "min_child_weight": 5,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,               # L1 regularization
        "reg_lambda": 1.0,              # L2 regularization
        "scale_pos_weight": 1.0,        # Ajustar si hay desbalance
        "random_state": 42,
        "n_jobs": -1,
    })
    
    # ─── LightGBM Hyperparameters ───────────────────────────────────
    lgb_params: Dict[str, Any] = field(default_factory=lambda: {
        "objective": "binary",
        "metric": "auc",
        "max_depth": 4,
        "learning_rate": 0.05,
        "n_estimators": 300,
        "min_child_samples": 20,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    })
    
    # ─── RandomForest Hyperparameters ───────────────────────────────
    rf_params: Dict[str, Any] = field(default_factory=lambda: {
        "n_estimators": 200,
        "max_depth": 6,
        "min_samples_split": 10,
        "min_samples_leaf": 5,
        "max_features": "sqrt",
        "random_state": 42,
        "n_jobs": -1,
    })
    
    # ─── Early Stopping ─────────────────────────────────────────────
    early_stopping_rounds: int = 30
    validation_fraction: float = 0.15   # Validation set para early stopping
    
    # ─── Threshold de Inferencia ────────────────────────────────────
    default_threshold: float = 0.55     # Probabilidad mínima para señal
    dynamic_threshold: bool = True      # Ajustar threshold dinámicamente
    min_threshold: float = 0.50
    max_threshold: float = 0.75
    
    # ─── Reentrenamiento ────────────────────────────────────────────
    retrain_interval_days: int = 7      # Reentrenar cada 7 días
    min_new_trades: int = 50            # Mínimo trades nuevos para reentrenar
    keep_versions: int = 5              # Versiones de modelo a mantener
    
    # ─── Business Metrics ───────────────────────────────────────────
    min_profit_factor: float = 1.2      # PF mínimo aceptable
    min_win_rate: float = 0.45          # Win rate mínimo
    max_drawdown_pct: float = 0.20      # Drawdown máximo permitido
    
    # ─── Feature Engineering ────────────────────────────────────────
    normalize_features: bool = True     # Z-score normalization
    handle_outliers: bool = True        # Clip outliers a 3 std
    fill_missing: str = "median"        # "median", "mean", "zero"
    
    def __post_init__(self):
        """Crear directorios si no existen."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def get_all_features(self) -> List[str]:
        """Retorna lista completa de features numéricas."""
        return self.core_features + self.extended_features
    
    def get_model_params(self) -> Dict[str, Any]:
        """Retorna parámetros según el tipo de modelo."""
        if self.model_type == ModelType.XGBOOST:
            return self.xgb_params.copy()
        elif self.model_type == ModelType.LIGHTGBM:
            return self.lgb_params.copy()
        elif self.model_type == ModelType.RANDOM_FOREST:
            return self.rf_params.copy()
        else:
            # Logistic Regression
            return {
                "penalty": "l2",
                "C": 1.0,
                "solver": "lbfgs",
                "max_iter": 1000,
                "random_state": 42,
            }


# ─── Configuración por defecto (singleton) ──────────────────────────
default_config = MLConfig()
