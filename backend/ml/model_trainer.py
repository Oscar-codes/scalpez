"""
QuantPulse – Model Trainer (Validación Temporal + Business Metrics)
=====================================================================
Entrenamiento de modelos ML con enfoque en métricas de negocio.

MODELOS SOPORTADOS:
  - XGBoost (default): Óptimo para datos tabulares
  - LightGBM: Rápido, bueno para grandes datasets
  - RandomForest: Robusto, interpretable
  - LogisticRegression: Baseline lineal

VALIDACIÓN:
  - Time-based split: Train pasado, Test futuro
  - Walk-forward CV: Rolling window
  - Early stopping: Previene sobreajuste

MÉTRICAS:
  - Clásicas: ROC-AUC, Precision, Recall, F1
  - Negocio: Profit Factor, Expectancy, Win Rate simulado

POR QUÉ XGBoost PARA DATOS FINANCIEROS:
  1. Maneja relaciones no lineales (EMA × RSI × volatilidad)
  2. Robusto ante outliers (común en mercados)
  3. Feature importance interpretable (explicabilidad)
  4. Regularización integrada (evita overfit)
  5. Eficiente con datasets medianos (100-100K samples)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
    confusion_matrix,
    classification_report,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

# Importaciones condicionales para modelos gradient boosting
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from backend.ml.config import MLConfig, ModelType, default_config

logger = logging.getLogger("quantpulse.ml.trainer")


class TrainingResult:
    """Resultado completo de un entrenamiento."""
    
    def __init__(
        self,
        model: Any,
        metrics: Dict[str, float],
        feature_importance: Dict[str, float],
        threshold: float,
        training_time: float,
        config: MLConfig,
        n_train: int,
        n_test: int,
    ):
        self.model = model
        self.metrics = metrics
        self.feature_importance = feature_importance
        self.threshold = threshold
        self.training_time = training_time
        self.config = config
        self.n_train = n_train
        self.n_test = n_test
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario (sin el modelo)."""
        return {
            "metrics": self.metrics,
            "feature_importance": self.feature_importance,
            "threshold": self.threshold,
            "training_time": self.training_time,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "timestamp": self.timestamp.isoformat(),
            "model_type": self.config.model_type.value,
        }
    
    def __repr__(self) -> str:
        return (
            f"TrainingResult("
            f"AUC={self.metrics.get('roc_auc', 0):.4f}, "
            f"PF={self.metrics.get('profit_factor', 0):.2f}, "
            f"WinRate={self.metrics.get('win_rate', 0):.2%})"
        )


class ModelTrainer:
    """
    Entrena modelos ML con validación temporal y métricas de negocio.
    
    FILOSOFÍA:
      No optimizamos accuracy. Optimizamos Profit Factor y Expectancy.
      Un modelo con 55% accuracy pero PF=1.5 es mejor que uno
      con 65% accuracy pero PF=1.0.
    
    USO:
        trainer = ModelTrainer(config)
        result = trainer.train(X_train, X_test, y_train, y_test, feature_names)
        trainer.save_model(result, "v1.0.0")
    """
    
    def __init__(self, config: MLConfig = None):
        self._config = config or default_config
        self._model = None
        self._last_result: Optional[TrainingResult] = None
    
    # ════════════════════════════════════════════════════════════════
    #  FACTORY DE MODELOS
    # ════════════════════════════════════════════════════════════════
    
    def _create_model(self, model_type: ModelType = None) -> Any:
        """
        Crea instancia del modelo según configuración.
        
        JUSTIFICACIÓN DE ELECCIÓN:
        
        XGBoost (RECOMENDADO):
          - Gradient boosting optimizado
          - Regularización L1/L2 integrada
          - Maneja missing values nativamente
          - Early stopping para evitar overfit
        
        LightGBM:
          - Más rápido que XGBoost en grandes datasets
          - Leaf-wise growth (vs level-wise de XGB)
          - Menor consumo de memoria
        
        RandomForest:
          - Más simple y estable
          - Menos propenso a overfit sin tuning
          - Feature importance clara
        
        LogisticRegression:
          - Baseline lineal
          - Rápido para comparación
        """
        model_type = model_type or self._config.model_type
        params = self._config.get_model_params()
        
        if model_type == ModelType.XGBOOST:
            if not HAS_XGBOOST:
                raise ImportError("XGBoost no instalado. pip install xgboost")
            return xgb.XGBClassifier(**params)
        
        elif model_type == ModelType.LIGHTGBM:
            if not HAS_LIGHTGBM:
                raise ImportError("LightGBM no instalado. pip install lightgbm")
            return lgb.LGBMClassifier(**params)
        
        elif model_type == ModelType.RANDOM_FOREST:
            return RandomForestClassifier(**params)
        
        elif model_type == ModelType.LOGISTIC:
            return LogisticRegression(**params)
        
        else:
            raise ValueError(f"Modelo no soportado: {model_type}")
    
    # ════════════════════════════════════════════════════════════════
    #  ENTRENAMIENTO
    # ════════════════════════════════════════════════════════════════
    
    def train(
        self,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        feature_names: List[str],
        actual_rr: np.ndarray = None,  # Para métricas de negocio
        pnl_pct: np.ndarray = None,
    ) -> TrainingResult:
        """
        Entrena modelo con early stopping y evalúa métricas.
        
        PROCESO:
          1. Crear validation set para early stopping
          2. Entrenar con early stopping
          3. Predecir probabilidades
          4. Calcular métricas clásicas
          5. Calcular métricas de negocio
          6. Determinar threshold óptimo
          7. Calcular feature importance
        
        Args:
            X_train: Features de entrenamiento
            X_test: Features de test
            y_train: Labels de entrenamiento
            y_test: Labels de test
            feature_names: Nombres de features para importancia
            actual_rr: RR real de cada trade (test) para PF
            pnl_pct: PnL % de cada trade (test) para Expectancy
        
        Returns:
            TrainingResult con modelo, métricas y threshold
        """
        start_time = time.time()
        
        # Validar inputs
        if len(X_train) < self._config.min_train_samples:
            raise ValueError(
                f"Train set muy pequeño: {len(X_train)}. "
                f"Mínimo: {self._config.min_train_samples}"
            )
        
        logger.info(
            "Iniciando entrenamiento: %s, Train=%d, Test=%d",
            self._config.model_type.value, len(X_train), len(X_test),
        )
        
        # Crear modelo
        model = self._create_model()
        
        # Configurar early stopping para gradient boosting
        fit_params = {}
        if self._config.model_type in [ModelType.XGBOOST, ModelType.LIGHTGBM]:
            # Split adicional para validation
            val_size = int(len(X_train) * self._config.validation_fraction)
            X_val = X_train[-val_size:]
            y_val = y_train[-val_size:]
            X_train_fit = X_train[:-val_size]
            y_train_fit = y_train[:-val_size]
            
            if self._config.model_type == ModelType.XGBOOST:
                fit_params = {
                    "eval_set": [(X_val, y_val)],
                    "verbose": False,
                }
                # XGBoost 2.0+ usa callbacks para early stopping
                model.set_params(
                    early_stopping_rounds=self._config.early_stopping_rounds
                )
            elif self._config.model_type == ModelType.LIGHTGBM:
                fit_params = {
                    "eval_set": [(X_val, y_val)],
                    "callbacks": [
                        lgb.early_stopping(self._config.early_stopping_rounds),
                        lgb.log_evaluation(period=0),  # Silenciar
                    ],
                }
        else:
            X_train_fit = X_train
            y_train_fit = y_train
        
        # Entrenar
        model.fit(X_train_fit, y_train_fit, **fit_params)
        self._model = model
        
        training_time = time.time() - start_time
        
        # Predecir probabilidades
        y_proba = model.predict_proba(X_test)[:, 1]
        
        # Encontrar threshold óptimo
        threshold = self._find_optimal_threshold(
            y_test, y_proba, actual_rr, pnl_pct
        )
        
        # Predicciones con threshold
        y_pred = (y_proba >= threshold).astype(int)
        
        # Calcular métricas
        metrics = self._calculate_metrics(
            y_test, y_pred, y_proba, actual_rr, pnl_pct, threshold
        )
        
        # Feature importance
        feature_importance = self._get_feature_importance(model, feature_names)
        
        # Crear resultado
        result = TrainingResult(
            model=model,
            metrics=metrics,
            feature_importance=feature_importance,
            threshold=threshold,
            training_time=training_time,
            config=self._config,
            n_train=len(X_train),
            n_test=len(X_test),
        )
        
        self._last_result = result
        
        logger.info(
            "Entrenamiento completado en %.2fs: AUC=%.4f, PF=%.2f, WR=%.2%%",
            training_time,
            metrics.get("roc_auc", 0),
            metrics.get("profit_factor", 0),
            metrics.get("win_rate", 0) * 100,
        )
        
        return result
    
    # ════════════════════════════════════════════════════════════════
    #  THRESHOLD OPTIMIZATION
    # ════════════════════════════════════════════════════════════════
    
    def _find_optimal_threshold(
        self,
        y_true: np.ndarray,
        y_proba: np.ndarray,
        actual_rr: np.ndarray = None,
        pnl_pct: np.ndarray = None,
    ) -> float:
        """
        Encuentra threshold óptimo para maximizar Profit Factor.
        
        PROCESO:
          1. Evaluar thresholds de 0.40 a 0.80
          2. Para cada threshold, simular filtrado de señales
          3. Calcular PF resultante
          4. Elegir threshold con mejor PF manteniendo suficientes trades
        
        RESTRICCIONES:
          - Mínimo 30% de trades deben pasar el filtro
          - Win rate no puede caer bajo 40%
        """
        best_threshold = self._config.default_threshold
        best_score = 0
        
        thresholds = np.arange(0.40, 0.80, 0.02)
        
        for thresh in thresholds:
            mask = y_proba >= thresh
            n_filtered = mask.sum()
            
            # Mínimo 30% de trades deben pasar
            if n_filtered < len(y_proba) * 0.30:
                continue
            
            filtered_true = y_true[mask]
            
            # Win rate filtrado
            win_rate = filtered_true.mean() if len(filtered_true) > 0 else 0
            
            # Si tenemos RR/PnL reales, calcular PF
            if actual_rr is not None and len(actual_rr) > 0:
                filtered_rr = actual_rr[mask]
                wins = filtered_rr[filtered_true == 1]
                losses = filtered_rr[filtered_true == 0]
                
                total_win = np.abs(wins).sum() if len(wins) > 0 else 0
                total_loss = np.abs(losses).sum() if len(losses) > 0 else 1
                pf = total_win / total_loss if total_loss > 0 else total_win
            else:
                # Aproximar PF con win rate y RR default
                avg_rr = 2.0
                pf = (win_rate * avg_rr) / ((1 - win_rate) * 1) if win_rate < 1 else 10
            
            # Score combinado: PF × sqrt(n_trades) × win_rate
            # Preferimos PF alto pero con suficientes trades
            score = pf * np.sqrt(n_filtered / len(y_proba)) * win_rate
            
            if score > best_score and win_rate >= 0.40:
                best_score = score
                best_threshold = thresh
        
        logger.debug(
            "Threshold óptimo: %.2f (score=%.4f)",
            best_threshold, best_score,
        )
        
        return best_threshold
    
    # ════════════════════════════════════════════════════════════════
    #  MÉTRICAS
    # ════════════════════════════════════════════════════════════════
    
    def _calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray,
        actual_rr: np.ndarray = None,
        pnl_pct: np.ndarray = None,
        threshold: float = 0.5,
    ) -> Dict[str, float]:
        """
        Calcula métricas clásicas y de negocio.
        
        MÉTRICAS CLÁSICAS:
          - ROC-AUC: Discriminación general
          - Precision: ¿Qué % de PROFIT predichos son reales?
          - Recall: ¿Qué % de PROFIT reales detectamos?
          - F1: Balance precision/recall
          - Accuracy: Aciertos totales (menos importante)
        
        MÉTRICAS DE NEGOCIO (CRÍTICAS):
          - Win Rate: % trades ganadores
          - Profit Factor: Sum(wins) / Sum(losses)
          - Expectancy: E[PnL] por trade
          - Filtered Win Rate: Win rate aplicando threshold
        """
        metrics = {}
        
        # ── Métricas clásicas ──────────────────────────────────────
        metrics["roc_auc"] = roc_auc_score(y_true, y_proba)
        metrics["precision"] = precision_score(y_true, y_pred, zero_division=0)
        metrics["recall"] = recall_score(y_true, y_pred, zero_division=0)
        metrics["f1"] = f1_score(y_true, y_pred, zero_division=0)
        metrics["accuracy"] = accuracy_score(y_true, y_pred)
        
        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred)
        if cm.shape == (2, 2):
            tn, fp, fn, tp = cm.ravel()
            metrics["true_negatives"] = int(tn)
            metrics["false_positives"] = int(fp)
            metrics["false_negatives"] = int(fn)
            metrics["true_positives"] = int(tp)
        
        # ── Métricas de negocio ────────────────────────────────────
        
        # Win rate base (sin filtro)
        metrics["base_win_rate"] = y_true.mean()
        
        # Win rate filtrado (aplicando threshold)
        mask = y_proba >= threshold
        if mask.sum() > 0:
            metrics["filtered_win_rate"] = y_true[mask].mean()
            metrics["filtered_trades"] = int(mask.sum())
            metrics["filter_rate"] = mask.sum() / len(y_true)
        else:
            metrics["filtered_win_rate"] = 0
            metrics["filtered_trades"] = 0
            metrics["filter_rate"] = 0
        
        # Alias para compatibilidad
        metrics["win_rate"] = metrics["filtered_win_rate"]
        
        # Profit Factor (si tenemos RR real)
        if actual_rr is not None and len(actual_rr) > 0:
            filtered_rr = actual_rr[mask] if mask.sum() > 0 else np.array([])
            filtered_true = y_true[mask] if mask.sum() > 0 else np.array([])
            
            if len(filtered_rr) > 0:
                wins = filtered_rr[filtered_true == 1]
                losses = filtered_rr[filtered_true == 0]
                
                total_win = np.abs(wins).sum() if len(wins) > 0 else 0
                total_loss = np.abs(losses).sum() if len(losses) > 0 else 0
                
                metrics["profit_factor"] = (
                    total_win / total_loss if total_loss > 0 else 10.0
                )
                metrics["avg_win_rr"] = wins.mean() if len(wins) > 0 else 0
                metrics["avg_loss_rr"] = losses.mean() if len(losses) > 0 else 0
            else:
                metrics["profit_factor"] = 0
        else:
            # Aproximar con win rate y RR default (2.0)
            wr = metrics["filtered_win_rate"]
            rr = 2.0
            metrics["profit_factor"] = (wr * rr) / ((1 - wr) * 1) if wr < 1 else 10.0
        
        # Expectancy (si tenemos PnL real)
        if pnl_pct is not None and len(pnl_pct) > 0:
            filtered_pnl = pnl_pct[mask] if mask.sum() > 0 else np.array([])
            metrics["expectancy"] = filtered_pnl.mean() if len(filtered_pnl) > 0 else 0
        else:
            # Aproximar: E = WR × AvgWin - (1-WR) × AvgLoss
            wr = metrics["filtered_win_rate"]
            metrics["expectancy"] = wr * 2.0 - (1 - wr) * 1.0  # Asumiendo RR 2:1
        
        # Improvement sobre baseline
        if metrics["base_win_rate"] > 0:
            metrics["win_rate_improvement"] = (
                (metrics["filtered_win_rate"] - metrics["base_win_rate"]) 
                / metrics["base_win_rate"]
            )
        else:
            metrics["win_rate_improvement"] = 0
        
        return metrics
    
    # ════════════════════════════════════════════════════════════════
    #  FEATURE IMPORTANCE
    # ════════════════════════════════════════════════════════════════
    
    def _get_feature_importance(
        self,
        model: Any,
        feature_names: List[str],
    ) -> Dict[str, float]:
        """
        Extrae importancia de features del modelo.
        
        INTERPRETACIÓN:
          - XGBoost/LightGBM: gain (contribución al split)
          - RandomForest: mean decrease impurity
          - Logistic: coeficientes absolutos
        
        Las features más importantes indican qué condiciones
        tienen mayor poder predictivo para trades ganadores.
        """
        importance = {}
        
        try:
            if hasattr(model, "feature_importances_"):
                # XGBoost, LightGBM, RandomForest
                raw_importance = model.feature_importances_
            elif hasattr(model, "coef_"):
                # Logistic Regression
                raw_importance = np.abs(model.coef_[0])
            else:
                return {}
            
            # Normalizar a suma = 1
            total = raw_importance.sum()
            if total > 0:
                normalized = raw_importance / total
            else:
                normalized = raw_importance
            
            # Mapear a nombres
            for i, name in enumerate(feature_names):
                if i < len(normalized):
                    importance[name] = float(normalized[i])
            
            # Ordenar por importancia
            importance = dict(
                sorted(importance.items(), key=lambda x: x[1], reverse=True)
            )
            
        except Exception as e:
            logger.warning("Error extrayendo feature importance: %s", e)
        
        return importance
    
    # ════════════════════════════════════════════════════════════════
    #  WALK-FORWARD VALIDATION
    # ════════════════════════════════════════════════════════════════
    
    def walk_forward_validation(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        n_splits: int = None,
    ) -> Dict[str, Any]:
        """
        Walk-forward cross-validation temporal.
        
        PROCESO:
          Para cada fold:
            1. Train con datos hasta fold N
            2. Test con datos del fold N+1
            3. Calcular métricas
          
          Agregar métricas promedio y std.
        
        VENTAJAS:
          - Simula backtesting real
          - Detecta si modelo es estable en diferentes períodos
          - Identifica regime changes donde modelo falla
        
        Returns:
            {
                "fold_metrics": [...],
                "mean_metrics": {...},
                "std_metrics": {...},
                "stable": bool,
            }
        """
        n_splits = n_splits or self._config.n_splits
        
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_metrics = []
        
        logger.info("Walk-forward validation: %d folds", n_splits)
        
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train_fold = X[train_idx]
            X_test_fold = X[test_idx]
            y_train_fold = y[train_idx]
            y_test_fold = y[test_idx]
            
            # Entrenar modelo para este fold
            model = self._create_model()
            model.fit(X_train_fold, y_train_fold)
            
            # Predecir
            y_proba = model.predict_proba(X_test_fold)[:, 1]
            y_pred = (y_proba >= self._config.default_threshold).astype(int)
            
            # Métricas del fold
            fold_result = {
                "fold": fold + 1,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "roc_auc": roc_auc_score(y_test_fold, y_proba),
                "precision": precision_score(y_test_fold, y_pred, zero_division=0),
                "recall": recall_score(y_test_fold, y_pred, zero_division=0),
                "f1": f1_score(y_test_fold, y_pred, zero_division=0),
                "win_rate": y_test_fold[y_proba >= self._config.default_threshold].mean()
                if (y_proba >= self._config.default_threshold).sum() > 0 else 0,
            }
            
            fold_metrics.append(fold_result)
            
            logger.debug(
                "Fold %d: AUC=%.4f, F1=%.4f, WR=%.2f%%",
                fold + 1,
                fold_result["roc_auc"],
                fold_result["f1"],
                fold_result["win_rate"] * 100,
            )
        
        # Agregar métricas
        metric_keys = ["roc_auc", "precision", "recall", "f1", "win_rate"]
        mean_metrics = {
            k: np.mean([f[k] for f in fold_metrics])
            for k in metric_keys
        }
        std_metrics = {
            k: np.std([f[k] for f in fold_metrics])
            for k in metric_keys
        }
        
        # Determinar estabilidad (low variance across folds)
        stable = all(
            std_metrics[k] < 0.10  # Max 10% std
            for k in ["roc_auc", "f1"]
        )
        
        result = {
            "fold_metrics": fold_metrics,
            "mean_metrics": mean_metrics,
            "std_metrics": std_metrics,
            "stable": stable,
            "n_splits": n_splits,
        }
        
        logger.info(
            "Walk-forward completo: AUC=%.4f±%.4f, F1=%.4f±%.4f, Stable=%s",
            mean_metrics["roc_auc"],
            std_metrics["roc_auc"],
            mean_metrics["f1"],
            std_metrics["f1"],
            stable,
        )
        
        return result
    
    # ════════════════════════════════════════════════════════════════
    #  COMPARACIÓN DE MODELOS
    # ════════════════════════════════════════════════════════════════
    
    def compare_models(
        self,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        feature_names: List[str],
    ) -> Dict[str, Dict[str, float]]:
        """
        Compara todos los modelos disponibles.
        
        Returns:
            {
                "xgboost": {"roc_auc": ..., "profit_factor": ...},
                "lightgbm": {...},
                "random_forest": {...},
                "logistic_regression": {...},
            }
        """
        results = {}
        
        models_to_test = [ModelType.RANDOM_FOREST, ModelType.LOGISTIC]
        if HAS_XGBOOST:
            models_to_test.insert(0, ModelType.XGBOOST)
        if HAS_LIGHTGBM:
            models_to_test.insert(1, ModelType.LIGHTGBM)
        
        for model_type in models_to_test:
            try:
                logger.info("Evaluando %s...", model_type.value)
                
                # Cambiar temporalmente el tipo de modelo
                original_type = self._config.model_type
                self._config.model_type = model_type
                
                result = self.train(
                    X_train, X_test, y_train, y_test, feature_names
                )
                
                results[model_type.value] = {
                    "roc_auc": result.metrics.get("roc_auc", 0),
                    "precision": result.metrics.get("precision", 0),
                    "recall": result.metrics.get("recall", 0),
                    "f1": result.metrics.get("f1", 0),
                    "profit_factor": result.metrics.get("profit_factor", 0),
                    "win_rate": result.metrics.get("win_rate", 0),
                    "training_time": result.training_time,
                }
                
                # Restaurar
                self._config.model_type = original_type
                
            except Exception as e:
                logger.error("Error evaluando %s: %s", model_type.value, e)
                results[model_type.value] = {"error": str(e)}
        
        # Ordenar por Profit Factor
        sorted_results = dict(
            sorted(
                results.items(),
                key=lambda x: x[1].get("profit_factor", 0),
                reverse=True,
            )
        )
        
        best_model = list(sorted_results.keys())[0]
        logger.info(
            "Mejor modelo por PF: %s (PF=%.2f, AUC=%.4f)",
            best_model,
            sorted_results[best_model].get("profit_factor", 0),
            sorted_results[best_model].get("roc_auc", 0),
        )
        
        return sorted_results
    
    # ════════════════════════════════════════════════════════════════
    #  GETTERS
    # ════════════════════════════════════════════════════════════════
    
    def get_model(self) -> Any:
        """Retorna el modelo entrenado."""
        return self._model
    
    def get_last_result(self) -> Optional[TrainingResult]:
        """Retorna el último resultado de entrenamiento."""
        return self._last_result
