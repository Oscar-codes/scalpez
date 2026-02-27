"""
QuantPulse – Domain Entity: Candle
====================================
Vela OHLCV inmutable construida a partir de ticks agregados.

Decisiones de diseño:
- frozen=True → inmutable una vez cerrada, EVITA REPAINTING.
  Nadie puede alterar una vela pasada, garantizando integridad histórica.
- Se usa dataclass por rendimiento (más ligera que Pydantic para hot-path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candle:
    """Vela OHLCV con timestamp de apertura."""

    symbol: str          # e.g. "R_100"
    timestamp: float     # epoch de apertura (time.time())
    open: float
    high: float
    low: float
    close: float
    tick_count: int      # cantidad de ticks que componen esta vela
    interval: int        # duración en segundos de la vela

    def to_dict(self) -> dict:
        """Serialización para WebSocket / frontend."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_count": self.tick_count,
            "interval": self.interval,
        }
