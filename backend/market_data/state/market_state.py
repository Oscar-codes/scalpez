"""
Market Data – Market State Manager
===================================
Re-exporta MarketStateManager desde backend.app.state para compatibilidad.
"""

from backend.app.state.market_state import MarketStateManager

__all__ = ["MarketStateManager"]
