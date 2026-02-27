"""
Presentation – API Routes
==========================
Re-exporta routes desde backend.app.api para compatibilidad.
"""

from backend.app.api.routes import router, init_routes

__all__ = ["router", "init_routes"]
