"""
Market Data – Deriv Client
===========================
Re-exporta DerivClient desde backend.app.infrastructure para compatibilidad.
"""

from backend.app.infrastructure.deriv_client import DerivClient

__all__ = ["DerivClient"]
