"""
Market Data – Indicator Service
================================
Re-exporta IndicatorService desde backend.app.services para compatibilidad.
"""

from backend.app.services.indicator_service import IndicatorService

__all__ = ["IndicatorService"]
