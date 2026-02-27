"""
QuantPulse – Settings (DEPRECATED: use backend.shared.config.settings)
======================================================================
Este archivo se mantiene por compatibilidad con imports legacy.
La versión canónica está en backend/shared/config/settings.py

Todos los nuevos imports deben usar:
    from backend.shared.config.settings import Settings, settings
"""

from backend.shared.config.settings import Settings, settings

__all__ = ["Settings", "settings"]
