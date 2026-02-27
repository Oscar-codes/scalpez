"""
QuantPulse – Logging (DEPRECATED: use backend.shared.logging.logger)
====================================================================
Este archivo se mantiene por compatibilidad con imports legacy.
La versión canónica está en backend/shared/logging/logger.py

Todos los nuevos imports deben usar:
    from backend.shared.logging.logger import setup_logging, get_logger
"""

from backend.shared.logging.logger import setup_logging, get_logger

__all__ = ["setup_logging", "get_logger"]
