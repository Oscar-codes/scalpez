"""
Market Data – Indicator State Manager
======================================
Re-exporta IndicatorStateManager desde backend.app.state para compatibilidad.
"""

from backend.app.state.indicator_state import IndicatorStateManager

__all__ = ["IndicatorStateManager"]
