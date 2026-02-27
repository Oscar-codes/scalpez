"""
QuantPulse – Trade State (Placeholder – Fase futura)
=====================================================
Gestionará el estado de trades activos y simulados.
Fase 1: solo estructura base.
"""

from __future__ import annotations


class TradeStateManager:
    """Placeholder para gestión de estado de trades."""

    def __init__(self) -> None:
        self._active_trades: dict = {}

    def has_active_trade(self, symbol: str) -> bool:
        return symbol in self._active_trades
