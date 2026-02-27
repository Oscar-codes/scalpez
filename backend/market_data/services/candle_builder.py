"""
Market Data – Candle Builder
==============================
Re-exporta CandleBuilder desde backend.app.services para compatibilidad.
"""

from backend.app.services.candle_builder import CandleBuilder

__all__ = ["CandleBuilder"]
