"""
Market Data – Event Bus
========================
Re-exporta EventBus desde backend.app.infrastructure para compatibilidad.
"""

from backend.app.infrastructure.event_bus import EventBus

__all__ = ["EventBus"]
