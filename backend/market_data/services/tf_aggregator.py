"""
Market Data – Timeframe Aggregator
===================================
Re-exporta TimeframeAggregator desde backend.app.services para compatibilidad.
"""

from backend.app.services.timeframe_aggregator import TimeframeAggregator

__all__ = ["TimeframeAggregator"]
