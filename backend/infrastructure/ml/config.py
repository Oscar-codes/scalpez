"""
QuantPulse – ML Configuration
===============================
Configuración centralizada para Machine Learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class MLConfig:
    """
    Configuración para el módulo de ML.
    
    HIPERPARÁMETROS:
    - Se usan valores conservadores para evitar overfitting
    - max_depth bajo para simplicidad interpretable
    - Early stopping para regularización automática
    """
    
    # ═══════════════════════════════════════════════════════════════
    #  MODELO
    # ═══════════════════════════════════════════════════════════════
    
    model_type: str = "xgboost"  # xgboost | lightgbm | random_forest | logistic
    
    # XGBoost específico
    n_estimators: int = 200
    max_depth: int = 4
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1  # L1
    reg_lambda: float = 1.0  # L2
    
    # Early stopping
    early_stopping_rounds: int = 30
    eval_metric: str = "auc"
    
    # ═══════════════════════════════════════════════════════════════
    #  FEATURES
    # ═══════════════════════════════════════════════════════════════
    
    feature_columns: List[str] = field(default_factory=lambda: [
        "ema_distance",           # (ema9 - ema21) / ema21
        "rsi_value",
        "rsi_slope",              # rsi - prev_rsi
        "volatility_20",          # stddev(close, 20)
        "candle_body_ratio",      # |close - open| / (high - low)
        "distance_to_support",    # (close - support) / close
        "distance_to_resistance", # (resistance - close) / close
        "momentum_5",             # (close - close_5) / close_5
        "momentum_10",
        "rr_ratio",               # Risk-Reward de la señal
        "hour_of_day",            # Feature temporal
        "day_of_week",
    ])
    
    categorical_features: List[str] = field(default_factory=lambda: [
        "signal_type",            # BUY | SELL
        "dominant_condition",     # ema_cross | rsi_reversal | etc.
    ])
    
    # ═══════════════════════════════════════════════════════════════
    #  VALIDACIÓN
    # ═══════════════════════════════════════════════════════════════
    
    test_size: float = 0.2
    time_split: bool = True  # Usar split temporal, no random
    min_samples_train: int = 100
    walk_forward_folds: int = 5
    
    # ═══════════════════════════════════════════════════════════════
    #  THRESHOLD
    # ═══════════════════════════════════════════════════════════════
    
    default_threshold: float = 0.55
    threshold_range: Tuple[float, float] = (0.40, 0.80)
    threshold_optimization_metric: str = "profit_factor"  # profit_factor | win_rate | expectancy
    
    # ═══════════════════════════════════════════════════════════════
    #  RETRAINING
    # ═══════════════════════════════════════════════════════════════
    
    retrain_interval_days: int = 7
    min_new_samples: int = 50
    performance_decay_threshold: float = 0.1  # 10% decay triggers retrain
    
    # ═══════════════════════════════════════════════════════════════
    #  STORAGE
    # ═══════════════════════════════════════════════════════════════
    
    models_dir: str = "models"
    keep_last_n_versions: int = 5
