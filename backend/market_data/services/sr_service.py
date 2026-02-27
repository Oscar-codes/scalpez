"""
Market Data – Support/Resistance Service
==========================================
Re-exporta SupportResistanceService desde backend.app.services para compatibilidad.
"""

from backend.app.services.support_resistance_service import SupportResistanceService

__all__ = ["SupportResistanceService"]
