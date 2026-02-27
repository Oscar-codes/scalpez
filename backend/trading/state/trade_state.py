"""
Trading – Trade State Manager
==============================
Re-exporta TradeStateManager desde backend.app.state para compatibilidad.
En fase 5 se moverá el código completo aquí.
"""

from backend.app.state.trade_state import TradeStateManager

__all__ = ["TradeStateManager"]
