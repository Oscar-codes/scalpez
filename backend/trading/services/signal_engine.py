"""
Trading – Signal Engine
========================
Re-exporta SignalEngine desde backend.app.services para compatibilidad.
En fase 5 se moverá el código completo aquí.
"""

from backend.app.services.signal_engine import SignalEngine

__all__ = ["SignalEngine"]
