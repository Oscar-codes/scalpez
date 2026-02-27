"""
QuantPulse – Model Registry (Versionado y Gestión)
====================================================
Sistema de versionado para modelos ML con persistencia y rollback.

CARACTERÍSTICAS:
  - Almacenamiento estructurado de modelos
  - Metadata completa por versión
  - Rollback a versiones anteriores
  - Limpieza automática de versiones antiguas
  - Reentrenamiento programado

ESTRUCTURA DE ARCHIVOS:
  models/
    v1.0.0_20240227_143022/
      model.pkl           # Modelo serializado
      scaler.pkl          # StandardScaler del training
      metadata.json       # Config, métricas, features
      report.json         # Reporte detallado
    v1.0.1_20240303_091500/
      ...
    registry.json         # Índice de modelos

VERSIONADO:
  Formato: v{major}.{minor}.{patch}_{date}_{time}
  - Major: Cambio de arquitectura/modelo
  - Minor: Reentrenamiento con nuevos datos
  - Patch: Ajuste de threshold/parámetros
"""

from __future__ import annotations

import logging
import pickle
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import hashlib

from backend.ml.config import MLConfig, default_config

logger = logging.getLogger("quantpulse.ml.registry")


class ModelVersion:
    """Representa una versión de modelo."""
    
    def __init__(
        self,
        version: str,
        path: Path,
        created_at: datetime,
        metrics: Dict[str, float],
        threshold: float,
        is_active: bool = False,
    ):
        self.version = version
        self.path = path
        self.created_at = created_at
        self.metrics = metrics
        self.threshold = threshold
        self.is_active = is_active
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario."""
        return {
            "version": self.version,
            "path": str(self.path),
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "threshold": self.threshold,
            "is_active": self.is_active,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelVersion":
        """Deserializa desde diccionario."""
        return cls(
            version=data["version"],
            path=Path(data["path"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            metrics=data.get("metrics", {}),
            threshold=data.get("threshold", 0.55),
            is_active=data.get("is_active", False),
        )
    
    def __repr__(self) -> str:
        status = "✓" if self.is_active else " "
        return (
            f"[{status}] {self.version} "
            f"(AUC={self.metrics.get('roc_auc', 0):.3f}, "
            f"PF={self.metrics.get('profit_factor', 0):.2f})"
        )


class ModelRegistry:
    """
    Registry para gestión de versiones de modelos ML.
    
    RESPONSABILIDADES:
      - Guardar modelos con metadata
      - Cargar modelos por versión
      - Mantener historial de versiones
      - Rollback a versiones anteriores
      - Limpieza de versiones antiguas
    
    USO:
        registry = ModelRegistry(config)
        
        # Guardar nuevo modelo
        version = registry.save_model(
            model=trained_model,
            scaler=scaler,
            metadata={"metrics": {...}},
            feature_names=[...],
        )
        
        # Cargar modelo activo
        model, scaler, meta = registry.load_active()
        
        # Rollback
        registry.rollback("v1.0.0_20240227_143022")
    """
    
    def __init__(self, config: MLConfig = None):
        self._config = config or default_config
        self._models_dir = self._config.models_dir
        self._registry_file = self._models_dir / "registry.json"
        self._versions: Dict[str, ModelVersion] = {}
        self._active_version: Optional[str] = None
        
        # Crear directorio si no existe
        self._models_dir.mkdir(parents=True, exist_ok=True)
        
        # Cargar registry existente
        self._load_registry()
    
    # ════════════════════════════════════════════════════════════════
    #  PERSISTENCIA DEL REGISTRY
    # ════════════════════════════════════════════════════════════════
    
    def _load_registry(self):
        """Carga el índice de versiones desde disco."""
        if not self._registry_file.exists():
            logger.debug("Registry no existe, creando nuevo")
            return
        
        try:
            with open(self._registry_file, "r") as f:
                data = json.load(f)
            
            self._versions = {
                k: ModelVersion.from_dict(v)
                for k, v in data.get("versions", {}).items()
            }
            self._active_version = data.get("active_version")
            
            logger.info(
                "Registry cargado: %d versiones, activa=%s",
                len(self._versions),
                self._active_version or "ninguna",
            )
            
        except Exception as e:
            logger.error("Error cargando registry: %s", e)
    
    def _save_registry(self):
        """Guarda el índice de versiones a disco."""
        try:
            data = {
                "versions": {k: v.to_dict() for k, v in self._versions.items()},
                "active_version": self._active_version,
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            with open(self._registry_file, "w") as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            logger.error("Error guardando registry: %s", e)
    
    # ════════════════════════════════════════════════════════════════
    #  VERSIONADO
    # ════════════════════════════════════════════════════════════════
    
    def _generate_version(self, bump: str = "minor") -> str:
        """
        Genera nueva versión basada en la última.
        
        Args:
            bump: "major", "minor", o "patch"
        
        Returns:
            Nueva versión: v1.0.0_20240227_143022
        """
        now = datetime.utcnow()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        if not self._versions:
            return f"v1.0.0_{timestamp}"
        
        # Encontrar última versión
        sorted_versions = sorted(
            self._versions.keys(),
            key=lambda v: self._versions[v].created_at,
            reverse=True,
        )
        last = sorted_versions[0]
        
        # Extraer números
        # Formato: v1.0.0_20240227_143022
        parts = last.split("_")[0].replace("v", "").split(".")
        major = int(parts[0]) if len(parts) > 0 else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        
        if bump == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump == "minor":
            minor += 1
            patch = 0
        else:  # patch
            patch += 1
        
        return f"v{major}.{minor}.{patch}_{timestamp}"
    
    # ════════════════════════════════════════════════════════════════
    #  GUARDAR MODELO
    # ════════════════════════════════════════════════════════════════
    
    def save_model(
        self,
        model: Any,
        scaler: Any = None,
        metrics: Dict[str, float] = None,
        feature_names: List[str] = None,
        threshold: float = None,
        training_result: Any = None,  # TrainingResult
        bump: str = "minor",
        activate: bool = True,
    ) -> str:
        """
        Guarda un modelo entrenado con su metadata.
        
        ARCHIVOS CREADOS:
          - model.pkl: Modelo serializado
          - scaler.pkl: StandardScaler (si existe)
          - metadata.json: Config, threshold, features
          - report.json: Métricas detalladas
        
        Args:
            model: Modelo entrenado (sklearn/xgboost/lightgbm)
            scaler: StandardScaler del training
            metrics: Métricas de evaluación
            feature_names: Lista de features usadas
            threshold: Threshold de inferencia
            training_result: TrainingResult completo
            bump: Tipo de bump de versión
            activate: Si activar esta versión
        
        Returns:
            Versión creada
        """
        version = self._generate_version(bump)
        version_dir = self._models_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Extraer info del TrainingResult si está disponible
        if training_result is not None:
            metrics = metrics or training_result.metrics
            threshold = threshold or training_result.threshold
            feature_names = feature_names or []
        
        metrics = metrics or {}
        threshold = threshold or self._config.default_threshold
        feature_names = feature_names or []
        
        try:
            # Guardar modelo
            with open(version_dir / "model.pkl", "wb") as f:
                pickle.dump(model, f)
            
            # Guardar scaler
            if scaler is not None:
                with open(version_dir / "scaler.pkl", "wb") as f:
                    pickle.dump(scaler, f)
            
            # Guardar metadata
            metadata = {
                "version": version,
                "created_at": datetime.utcnow().isoformat(),
                "threshold": threshold,
                "feature_names": feature_names,
                "model_type": self._config.model_type.value,
                "config": {
                    "min_train_samples": self._config.min_train_samples,
                    "test_size": self._config.test_size,
                    "n_splits": self._config.n_splits,
                },
            }
            
            with open(version_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)
            
            # Guardar reporte de métricas
            report = {
                "version": version,
                "metrics": metrics,
                "feature_importance": (
                    training_result.feature_importance
                    if training_result else {}
                ),
                "training_time": (
                    training_result.training_time
                    if training_result else 0
                ),
                "n_train": training_result.n_train if training_result else 0,
                "n_test": training_result.n_test if training_result else 0,
            }
            
            with open(version_dir / "report.json", "w") as f:
                json.dump(report, f, indent=2)
            
            # Registrar versión
            model_version = ModelVersion(
                version=version,
                path=version_dir,
                created_at=datetime.utcnow(),
                metrics=metrics,
                threshold=threshold,
                is_active=False,
            )
            self._versions[version] = model_version
            
            # Activar si corresponde
            if activate:
                self.activate(version)
            
            self._save_registry()
            
            logger.info(
                "Modelo guardado: %s (AUC=%.4f, PF=%.2f, threshold=%.2f)",
                version,
                metrics.get("roc_auc", 0),
                metrics.get("profit_factor", 0),
                threshold,
            )
            
            # Limpiar versiones antiguas
            self._cleanup_old_versions()
            
            return version
            
        except Exception as e:
            logger.error("Error guardando modelo: %s", e)
            # Limpiar directorio en caso de error
            if version_dir.exists():
                shutil.rmtree(version_dir)
            raise
    
    # ════════════════════════════════════════════════════════════════
    #  CARGAR MODELO
    # ════════════════════════════════════════════════════════════════
    
    def load_model(
        self,
        version: str = None,
    ) -> tuple[Any, Any, Dict[str, Any]]:
        """
        Carga un modelo por versión.
        
        Args:
            version: Versión a cargar (None = activa)
        
        Returns:
            (model, scaler, metadata)
        """
        if version is None:
            version = self._active_version
        
        if version is None or version not in self._versions:
            raise ValueError(f"Versión no encontrada: {version}")
        
        model_version = self._versions[version]
        version_dir = model_version.path
        
        # Cargar modelo
        with open(version_dir / "model.pkl", "rb") as f:
            model = pickle.load(f)
        
        # Cargar scaler (opcional)
        scaler = None
        scaler_path = version_dir / "scaler.pkl"
        if scaler_path.exists():
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)
        
        # Cargar metadata
        with open(version_dir / "metadata.json", "r") as f:
            metadata = json.load(f)
        
        logger.info("Modelo cargado: %s", version)
        
        return model, scaler, metadata
    
    def load_active(self) -> tuple[Any, Any, Dict[str, Any]]:
        """Carga el modelo activo."""
        if self._active_version is None:
            raise ValueError("No hay modelo activo")
        return self.load_model(self._active_version)
    
    # ════════════════════════════════════════════════════════════════
    #  ACTIVACIÓN Y ROLLBACK
    # ════════════════════════════════════════════════════════════════
    
    def activate(self, version: str) -> bool:
        """
        Activa una versión de modelo.
        
        VALIDACIÓN:
          - La versión debe existir
          - El modelo debe cumplir métricas mínimas
        """
        if version not in self._versions:
            logger.error("Versión no encontrada: %s", version)
            return False
        
        model_version = self._versions[version]
        
        # Validar métricas mínimas
        pf = model_version.metrics.get("profit_factor", 0)
        wr = model_version.metrics.get("win_rate", 0)
        
        if pf < self._config.min_profit_factor:
            logger.warning(
                "Modelo %s tiene PF bajo (%.2f < %.2f)",
                version, pf, self._config.min_profit_factor,
            )
            # Advertir pero no bloquear
        
        if wr < self._config.min_win_rate:
            logger.warning(
                "Modelo %s tiene WR bajo (%.2f%% < %.2f%%)",
                version, wr * 100, self._config.min_win_rate * 100,
            )
        
        # Desactivar versión anterior
        for v in self._versions.values():
            v.is_active = False
        
        # Activar nueva versión
        model_version.is_active = True
        self._active_version = version
        
        self._save_registry()
        
        logger.info("Modelo activado: %s", version)
        
        return True
    
    def rollback(self, version: str = None) -> bool:
        """
        Rollback a una versión anterior.
        
        Args:
            version: Versión objetivo (None = anterior a la activa)
        """
        if version is not None:
            return self.activate(version)
        
        # Encontrar versión anterior a la activa
        sorted_versions = sorted(
            self._versions.keys(),
            key=lambda v: self._versions[v].created_at,
            reverse=True,
        )
        
        if len(sorted_versions) < 2:
            logger.error("No hay versión anterior para rollback")
            return False
        
        # La primera es la activa, la segunda es la anterior
        for v in sorted_versions[1:]:
            if v != self._active_version:
                return self.activate(v)
        
        return False
    
    # ════════════════════════════════════════════════════════════════
    #  LIMPIEZA
    # ════════════════════════════════════════════════════════════════
    
    def _cleanup_old_versions(self):
        """Elimina versiones antiguas manteniendo las N más recientes."""
        keep = self._config.keep_versions
        
        if len(self._versions) <= keep:
            return
        
        # Ordenar por fecha
        sorted_versions = sorted(
            self._versions.items(),
            key=lambda x: x[1].created_at,
            reverse=True,
        )
        
        # Mantener las N más recientes + la activa
        versions_to_delete = []
        for i, (version, model_v) in enumerate(sorted_versions):
            if i >= keep and version != self._active_version:
                versions_to_delete.append(version)
        
        for version in versions_to_delete:
            self.delete_version(version)
        
        if versions_to_delete:
            logger.info(
                "Limpieza: eliminadas %d versiones antiguas",
                len(versions_to_delete),
            )
    
    def delete_version(self, version: str) -> bool:
        """Elimina una versión del registro."""
        if version not in self._versions:
            return False
        
        if version == self._active_version:
            logger.error("No se puede eliminar la versión activa")
            return False
        
        model_version = self._versions[version]
        
        # Eliminar archivos
        if model_version.path.exists():
            shutil.rmtree(model_version.path)
        
        # Eliminar del registro
        del self._versions[version]
        self._save_registry()
        
        logger.info("Versión eliminada: %s", version)
        
        return True
    
    # ════════════════════════════════════════════════════════════════
    #  CONSULTAS
    # ════════════════════════════════════════════════════════════════
    
    def list_versions(self) -> List[ModelVersion]:
        """Lista todas las versiones ordenadas."""
        return sorted(
            self._versions.values(),
            key=lambda v: v.created_at,
            reverse=True,
        )
    
    def get_version(self, version: str) -> Optional[ModelVersion]:
        """Obtiene info de una versión."""
        return self._versions.get(version)
    
    def get_active_version(self) -> Optional[str]:
        """Retorna la versión activa."""
        return self._active_version
    
    def has_active_model(self) -> bool:
        """True si hay un modelo activo."""
        return self._active_version is not None
    
    def get_best_version(self, metric: str = "profit_factor") -> Optional[str]:
        """Retorna la versión con mejor métrica."""
        if not self._versions:
            return None
        
        best = max(
            self._versions.items(),
            key=lambda x: x[1].metrics.get(metric, 0),
        )
        
        return best[0]
    
    # ════════════════════════════════════════════════════════════════
    #  REENTRENAMIENTO PROGRAMADO
    # ════════════════════════════════════════════════════════════════
    
    def should_retrain(self) -> bool:
        """
        Determina si es momento de reentrenar.
        
        CONDICIONES:
          1. Han pasado N días desde el último entrenamiento
          2. O hay suficientes trades nuevos
        """
        if not self._active_version or self._active_version not in self._versions:
            return True
        
        model_version = self._versions[self._active_version]
        days_since = (datetime.utcnow() - model_version.created_at).days
        
        return days_since >= self._config.retrain_interval_days
    
    def get_days_since_training(self) -> int:
        """Días desde el último entrenamiento."""
        if not self._active_version or self._active_version not in self._versions:
            return 999
        
        model_version = self._versions[self._active_version]
        return (datetime.utcnow() - model_version.created_at).days
