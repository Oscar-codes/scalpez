"""
QuantPulse – Shared Module
============================
Utilidades transversales usadas por todas las capas.

Este módulo contiene:
- config/: Settings y configuración
- logging/: Setup de logging
- utils/: Helpers comunes

NOTA: Este módulo no contiene lógica de negocio.
"""

from backend.shared.config.settings import settings
from backend.shared.logging.logger import setup_logging, get_logger

__all__ = [
    "settings",
    "setup_logging",
    "get_logger",
]
