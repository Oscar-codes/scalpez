"""
QuantPulse – ML Training Pipeline (CLI)
=========================================
Script para entrenar y evaluar modelos ML.

USO:
    # Entrenar con datos recientes
    python -m backend.ml.train
    
    # Entrenar con rango de fechas
    python -m backend.ml.train --from 2024-01-01 --to 2024-02-27
    
    # Comparar modelos
    python -m backend.ml.train --compare
    
    # Walk-forward validation
    python -m backend.ml.train --walk-forward
    
    # Reentrenar modelo activo
    python -m backend.ml.train --retrain

FLUJO:
    1. Conectar a MySQL
    2. Construir dataset
    3. Entrenar modelo
    4. Evaluar métricas
    5. Guardar si mejora sobre modelo activo
"""

from __future__ import annotations

import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys
import json

# Agregar path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.ml.config import MLConfig, ModelType
from backend.ml.dataset_builder import DatasetBuilder
from backend.ml.model_trainer import ModelTrainer
from backend.ml.model_registry import ModelRegistry
from backend.app.infrastructure.database import db_manager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("quantpulse.ml.train")


async def run_training(
    config: MLConfig,
    min_date: datetime = None,
    max_date: datetime = None,
    compare_models: bool = False,
    walk_forward: bool = False,
):
    """
    Pipeline completo de entrenamiento.
    """
    logger.info("=" * 60)
    logger.info("  QuantPulse ML Training Pipeline")
    logger.info("=" * 60)
    
    # Inicializar componentes
    builder = DatasetBuilder(config)
    trainer = ModelTrainer(config)
    registry = ModelRegistry(config)
    
    # Conectar a BD
    logger.info("Conectando a MySQL...")
    await db_manager.initialize()
    
    try:
        async with db_manager.session() as session:
            # 1. Construir dataset
            logger.info("")
            logger.info("─" * 40)
            logger.info("  PASO 1: Construir Dataset")
            logger.info("─" * 40)
            
            X_train, X_test, y_train, y_test, feature_names = await builder.build_dataset(
                session,
                min_date=min_date,
                max_date=max_date,
            )
            
            logger.info("  Train: %d samples", len(X_train))
            logger.info("  Test:  %d samples", len(X_test))
            logger.info("  Features: %d", len(feature_names))
            
            # Mostrar distribución de clases
            train_win_rate = y_train.mean()
            test_win_rate = y_test.mean()
            logger.info("  Train Win Rate: %.2f%%", train_win_rate * 100)
            logger.info("  Test Win Rate:  %.2f%%", test_win_rate * 100)
            
            # 2. Walk-forward validation (opcional)
            if walk_forward:
                logger.info("")
                logger.info("─" * 40)
                logger.info("  PASO 2: Walk-Forward Validation")
                logger.info("─" * 40)
                
                import numpy as np
                X_all = np.vstack([X_train, X_test])
                y_all = np.concatenate([y_train, y_test])
                
                wf_result = trainer.walk_forward_validation(
                    X_all, y_all, feature_names, n_splits=5
                )
                
                logger.info("")
                logger.info("  Resultados por Fold:")
                for fold in wf_result["fold_metrics"]:
                    logger.info(
                        "    Fold %d: AUC=%.4f, F1=%.4f, WR=%.2f%%",
                        fold["fold"],
                        fold["roc_auc"],
                        fold["f1"],
                        fold["win_rate"] * 100,
                    )
                
                logger.info("")
                logger.info("  Promedio: AUC=%.4f±%.4f, F1=%.4f±%.4f",
                    wf_result["mean_metrics"]["roc_auc"],
                    wf_result["std_metrics"]["roc_auc"],
                    wf_result["mean_metrics"]["f1"],
                    wf_result["std_metrics"]["f1"],
                )
                logger.info("  Modelo estable: %s", 
                    "✓ Sí" if wf_result["stable"] else "✗ No"
                )
            
            # 3. Comparar modelos (opcional)
            if compare_models:
                logger.info("")
                logger.info("─" * 40)
                logger.info("  PASO 2: Comparación de Modelos")
                logger.info("─" * 40)
                
                comparison = trainer.compare_models(
                    X_train, X_test, y_train, y_test, feature_names
                )
                
                logger.info("")
                logger.info("  Ranking por Profit Factor:")
                for i, (model_name, metrics) in enumerate(comparison.items(), 1):
                    if "error" in metrics:
                        logger.info("    %d. %s: ERROR - %s", i, model_name, metrics["error"])
                    else:
                        logger.info(
                            "    %d. %s: PF=%.2f, AUC=%.4f, WR=%.2f%%",
                            i, model_name,
                            metrics.get("profit_factor", 0),
                            metrics.get("roc_auc", 0),
                            metrics.get("win_rate", 0) * 100,
                        )
            
            # 4. Entrenamiento final
            logger.info("")
            logger.info("─" * 40)
            logger.info("  PASO 3: Entrenamiento Final")
            logger.info("─" * 40)
            
            result = trainer.train(
                X_train, X_test, y_train, y_test, feature_names
            )
            
            logger.info("")
            logger.info("  Métricas de Evaluación:")
            logger.info("    ROC-AUC:      %.4f", result.metrics.get("roc_auc", 0))
            logger.info("    Precision:    %.4f", result.metrics.get("precision", 0))
            logger.info("    Recall:       %.4f", result.metrics.get("recall", 0))
            logger.info("    F1 Score:     %.4f", result.metrics.get("f1", 0))
            logger.info("")
            logger.info("  Métricas de Negocio:")
            logger.info("    Profit Factor: %.2f", result.metrics.get("profit_factor", 0))
            logger.info("    Win Rate:      %.2f%%", result.metrics.get("win_rate", 0) * 100)
            logger.info("    Expectancy:    %.4f", result.metrics.get("expectancy", 0))
            logger.info("    Threshold:     %.2f", result.threshold)
            logger.info("    Filter Rate:   %.2f%%", result.metrics.get("filter_rate", 0) * 100)
            logger.info("")
            logger.info("  Tiempo de entrenamiento: %.2fs", result.training_time)
            
            # 5. Feature Importance
            logger.info("")
            logger.info("─" * 40)
            logger.info("  PASO 4: Feature Importance (Top 10)")
            logger.info("─" * 40)
            
            top_features = list(result.feature_importance.items())[:10]
            for i, (feature, importance) in enumerate(top_features, 1):
                logger.info("    %2d. %-25s %.4f", i, feature, importance)
            
            # 6. Decisión de guardado
            logger.info("")
            logger.info("─" * 40)
            logger.info("  PASO 5: Guardar Modelo")
            logger.info("─" * 40)
            
            # Validar métricas mínimas
            pf = result.metrics.get("profit_factor", 0)
            wr = result.metrics.get("win_rate", 0)
            auc = result.metrics.get("roc_auc", 0)
            
            should_save = True
            reasons = []
            
            if pf < config.min_profit_factor:
                reasons.append(f"PF={pf:.2f} < mínimo={config.min_profit_factor}")
                should_save = False
            
            if wr < config.min_win_rate:
                reasons.append(f"WR={wr:.2%} < mínimo={config.min_win_rate:.2%}")
                should_save = False
            
            if auc < 0.55:
                reasons.append(f"AUC={auc:.4f} < mínimo=0.55")
                should_save = False
            
            # Comparar con modelo activo
            if registry.has_active_model():
                active_version = registry.get_active_version()
                active = registry.get_version(active_version)
                active_pf = active.metrics.get("profit_factor", 0)
                
                if pf <= active_pf:
                    reasons.append(
                        f"PF nuevo ({pf:.2f}) no supera activo ({active_pf:.2f})"
                    )
                    should_save = False
            
            if should_save:
                version = registry.save_model(
                    model=result.model,
                    scaler=builder.get_scaler(),
                    metrics=result.metrics,
                    feature_names=feature_names,
                    threshold=result.threshold,
                    training_result=result,
                    activate=True,
                )
                logger.info("  ✓ Modelo guardado: %s", version)
            else:
                logger.warning("  ✗ Modelo NO guardado:")
                for reason in reasons:
                    logger.warning("    - %s", reason)
            
            # Resumen final
            logger.info("")
            logger.info("=" * 60)
            logger.info("  RESUMEN")
            logger.info("=" * 60)
            logger.info("  Dataset:        %d train + %d test", len(X_train), len(X_test))
            logger.info("  Modelo:         %s", config.model_type.value)
            logger.info("  ROC-AUC:        %.4f", auc)
            logger.info("  Profit Factor:  %.2f", pf)
            logger.info("  Win Rate:       %.2f%%", wr * 100)
            logger.info("  Guardado:       %s", "✓ Sí" if should_save else "✗ No")
            logger.info("=" * 60)
            
    finally:
        await db_manager.close()


async def retrain_active_model(config: MLConfig):
    """Reentrenar modelo activo con datos recientes."""
    registry = ModelRegistry(config)
    
    if not registry.should_retrain():
        days = registry.get_days_since_training()
        logger.info(
            "Reentrenamiento no necesario. "
            "Último entrenamiento hace %d días (mínimo: %d)",
            days, config.retrain_interval_days
        )
        return
    
    logger.info("Iniciando reentrenamiento programado...")
    
    # Entrenar con datos de los últimos 30 días
    max_date = datetime.utcnow()
    min_date = max_date - timedelta(days=30)
    
    await run_training(config, min_date=min_date, max_date=max_date)


def main():
    parser = argparse.ArgumentParser(
        description="QuantPulse ML Training Pipeline"
    )
    
    parser.add_argument(
        "--from", dest="from_date", type=str,
        help="Fecha inicio (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--to", dest="to_date", type=str,
        help="Fecha fin (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Comparar todos los modelos"
    )
    parser.add_argument(
        "--walk-forward", action="store_true",
        help="Ejecutar walk-forward validation"
    )
    parser.add_argument(
        "--retrain", action="store_true",
        help="Reentrenar modelo si corresponde"
    )
    parser.add_argument(
        "--model", type=str, default="xgboost",
        choices=["xgboost", "lightgbm", "random_forest", "logistic"],
        help="Tipo de modelo"
    )
    
    args = parser.parse_args()
    
    # Configurar
    config = MLConfig()
    
    if args.model:
        config.model_type = ModelType(args.model)
    
    # Parsear fechas
    min_date = None
    max_date = None
    
    if args.from_date:
        min_date = datetime.strptime(args.from_date, "%Y-%m-%d")
    if args.to_date:
        max_date = datetime.strptime(args.to_date, "%Y-%m-%d")
    
    # Ejecutar
    if args.retrain:
        asyncio.run(retrain_active_model(config))
    else:
        asyncio.run(run_training(
            config,
            min_date=min_date,
            max_date=max_date,
            compare_models=args.compare,
            walk_forward=args.walk_forward,
        ))


if __name__ == "__main__":
    main()
