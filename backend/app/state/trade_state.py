"""
QuantPulse – Trade State Manager
=====================================================
Estado centralizado de trades simulados (paper trading).

DISEÑO:
  - Un solo trade activo por símbolo (no hedging en scalping).
  - Historial limitado (MAX_HISTORY) → protección de memoria.
  - Lookup O(1) para trade activo.
  - Stats computados bajo demanda (no almacenados).

THREADING:
  Todo corre en un solo event-loop asyncio. No se necesitan locks.
"""

from __future__ import annotations

from collections import deque

from ..domain.entities.trade import SimulatedTrade, TradeStatus

# ── Protección de memoria ──────────────────────────────────────
MAX_HISTORY = 500  # trades cerrados por símbolo


class TradeStateManager:
    """
    Estado en memoria de trades simulados.

    Invariantes:
      - Máximo 1 trade OPEN o PENDING por símbolo.
      - Historial con límite MAX_HISTORY por símbolo.
    """

    def __init__(self) -> None:
        # Trade activo por símbolo (PENDING u OPEN)
        self._active_trades: dict[str, SimulatedTrade] = {}
        # Historial de trades cerrados por símbolo
        self._closed_trades: dict[str, deque[SimulatedTrade]] = {}

    # ════════════════════════════════════════════════════════════════
    #  ESCRITURA
    # ════════════════════════════════════════════════════════════════

    def register_trade(self, trade: SimulatedTrade) -> bool:
        """
        Registra un nuevo trade si no hay uno activo para ese símbolo.

        Returns: True si se registró, False si ya hay uno activo.
        """
        if trade.symbol in self._active_trades:
            return False
        self._active_trades[trade.symbol] = trade
        return True

    def archive_trade(self, trade: SimulatedTrade) -> None:
        """
        Mueve un trade cerrado de activo → historial.

        Pre-condición: trade.is_closed debe ser True.
        """
        assert trade.is_closed, f"No se puede archivar trade {trade.status}"

        # Quitar de activos
        if trade.symbol in self._active_trades:
            if self._active_trades[trade.symbol].id == trade.id:
                del self._active_trades[trade.symbol]

        # Agregar a historial
        if trade.symbol not in self._closed_trades:
            self._closed_trades[trade.symbol] = deque(maxlen=MAX_HISTORY)
        self._closed_trades[trade.symbol].append(trade)

    # ════════════════════════════════════════════════════════════════
    #  CONSULTAS
    # ════════════════════════════════════════════════════════════════

    def has_active_trade(self, symbol: str) -> bool:
        """¿Hay un trade activo (PENDING u OPEN) para este símbolo?"""
        return symbol in self._active_trades

    def get_active_trade(self, symbol: str) -> SimulatedTrade | None:
        """Obtiene el trade activo de un símbolo."""
        return self._active_trades.get(symbol)

    def get_all_active_trades(self) -> list[SimulatedTrade]:
        """Todos los trades activos (para evaluación en cada tick)."""
        return list(self._active_trades.values())

    def get_closed_trades(self, symbol: str | None = None) -> list[SimulatedTrade]:
        """
        Historial de trades cerrados.
        Si symbol=None, devuelve todos los símbolos combinados.
        """
        if symbol:
            return list(self._closed_trades.get(symbol, []))
        all_trades: list[SimulatedTrade] = []
        for trades_deque in self._closed_trades.values():
            all_trades.extend(trades_deque)
        # Ordenar por close_timestamp descendente
        all_trades.sort(key=lambda t: t.close_timestamp, reverse=True)
        return all_trades

    # ════════════════════════════════════════════════════════════════
    #  ESTADÍSTICAS
    # ════════════════════════════════════════════════════════════════

    @property
    def stats(self) -> dict:
        """Estadísticas agregadas de paper trading."""
        all_closed = self.get_closed_trades()
        if not all_closed:
            return {
                "total_trades": 0,
                "active_trades": len(self._active_trades),
                "wins": 0,
                "losses": 0,
                "expired": 0,
                "win_rate": 0.0,
                "avg_pnl_percent": 0.0,
                "total_pnl_percent": 0.0,
                "best_trade_pnl": 0.0,
                "worst_trade_pnl": 0.0,
                "avg_duration_seconds": 0.0,
                "by_symbol": {},
            }

        wins = [t for t in all_closed if t.status == TradeStatus.PROFIT]
        losses = [t for t in all_closed if t.status == TradeStatus.LOSS]
        expired = [t for t in all_closed if t.status == TradeStatus.EXPIRED]

        total = len(all_closed)
        total_pnl = sum(t.pnl_percent for t in all_closed)
        pnl_values = [t.pnl_percent for t in all_closed]
        durations = [t.duration_seconds for t in all_closed if t.duration_seconds > 0]

        # Stats por símbolo
        symbols = set(t.symbol for t in all_closed)
        by_symbol: dict[str, dict] = {}
        for sym in symbols:
            sym_trades = [t for t in all_closed if t.symbol == sym]
            sym_wins = sum(1 for t in sym_trades if t.status == TradeStatus.PROFIT)
            sym_total = len(sym_trades)
            by_symbol[sym] = {
                "total": sym_total,
                "wins": sym_wins,
                "losses": sum(1 for t in sym_trades if t.status == TradeStatus.LOSS),
                "expired": sum(1 for t in sym_trades if t.status == TradeStatus.EXPIRED),
                "win_rate": round((sym_wins / sym_total) * 100, 1) if sym_total > 0 else 0.0,
                "total_pnl": round(sum(t.pnl_percent for t in sym_trades), 4),
            }

        return {
            "total_trades": total,
            "active_trades": len(self._active_trades),
            "wins": len(wins),
            "losses": len(losses),
            "expired": len(expired),
            "win_rate": round((len(wins) / total) * 100, 1) if total > 0 else 0.0,
            "avg_pnl_percent": round(total_pnl / total, 4) if total > 0 else 0.0,
            "total_pnl_percent": round(total_pnl, 4),
            "best_trade_pnl": round(max(pnl_values), 4) if pnl_values else 0.0,
            "worst_trade_pnl": round(min(pnl_values), 4) if pnl_values else 0.0,
            "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "by_symbol": by_symbol,
        }
