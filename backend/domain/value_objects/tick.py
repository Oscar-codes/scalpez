"""
QuantPulse – Domain Value Object: Tick
========================================
Representa un tick de mercado individual recibido de Deriv.

- frozen=True → inmutable, thread-safe para pasar entre coroutines.
- slots=True  → menor footprint de memoria en hot-path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tick:
    """Tick de precio atómico recibido del broker."""

    symbol: str       # Deriv symbol id (e.g. "R_100")
    epoch: float      # timestamp UNIX del broker
    quote: float      # precio actual
    ask: float | None = None  # spread ask (si disponible)
    bid: float | None = None  # spread bid (si disponible)

    def to_dict(self) -> dict:
        """Serialización para WebSocket / frontend."""
        return {
            "symbol": self.symbol,
            "epoch": self.epoch,
            "quote": self.quote,
            "ask": self.ask,
            "bid": self.bid,
        }
