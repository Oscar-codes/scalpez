"""
QuantPulse – Trade Simulator (Paper Trading Engine)
=====================================================
Motor de simulación de trades en papel en tiempo real.

═══════════════════════════════════════════════════════════════
            FLUJO DEL SIMULADOR
═══════════════════════════════════════════════════════════════

    Signal recibida
        │
        ▼
    ¿Hay trade activo para este símbolo?
        │
        ├── SÍ → Ignorar señal (log)
        │
        └── NO → Crear Trade PENDING
                    │
                  tick llega
                    │
                    ▼
               activate(tick.price) → Trade OPEN
                    │
                  tick llega (cada 1-5 seg)
                    │
                    ▼
               evaluate_tick(tick)
                    │
                    ├── BUY: price ≥ TP → PROFIT
                    ├── BUY: price ≤ SL → LOSS
                    ├── SELL: price ≤ TP → PROFIT
                    ├── SELL: price ≥ SL → LOSS
                    └── elapsed ≥ 30 min → EXPIRED

DISEÑO O(1):
    evaluate_tick() no itera sobre nada – es una simple comparación
    de 2-3 valores numéricos por trade activo. Para 3 símbolos con
    máximo 1 trade activo cada uno, es O(3) = O(1) por tick.

ANTI-BIAS:
    Toda la información usada para abrir/cerrar un trade proviene
    de ticks que ya ocurrieron. No se usa el precio futuro del siguiente
    tick – se usa el precio del tick ACTUAL.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from ..core.settings import settings
from ..domain.entities.signal import Signal
from ..domain.entities.trade import SimulatedTrade, TradeStatus
from ..state.trade_state import TradeStateManager

logger = logging.getLogger("quantpulse.trade_simulator")

# Importación condicional para evitar dependencia circular
# StatsEngine se inyecta como Optional en __init__
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .stats_engine import StatsEngine


class TradeSimulator:
    """
    Motor de Paper Trading.

    Responsabilidades:
      1. Crear trades a partir de señales (state: PENDING)
      2. Activar trades al primer tick posterior (PENDING → OPEN)
      3. Evaluar TP/SL/Expiración en cada tick (OPEN → cerrado)
      4. Delegar persistencia de estado a TradeStateManager
    """

    def __init__(self, trade_state: TradeStateManager, stats_engine: "StatsEngine | None" = None) -> None:
        self._state = trade_state
        self._stats_engine = stats_engine
        self._max_duration_seconds = settings.max_trade_duration * 60  # min → seg
        self._stats = _SimulatorStats()

    # ════════════════════════════════════════════════════════════════
    #  1. ABRIR TRADE (Signal → PENDING)
    # ════════════════════════════════════════════════════════════════

    def open_trade(self, signal: Signal) -> SimulatedTrade | None:
        """
        Crea un trade simulado en estado PENDING a partir de una señal.

        Returns:
            SimulatedTrade si se creó exitosamente, None si ya hay un trade activo.

        NOTA ANTI-BIAS:
            El trade NO se ejecuta al precio de la señal (signal.entry).
            Se queda PENDING hasta que llegue el siguiente tick, y ahí se
            ejecuta al precio real de ese tick. Eso modela el slippage real.
        """
        # ── Guard: ya hay trade activo para este símbolo ──
        if self._state.has_active_trade(signal.symbol):
            existing = self._state.get_active_trade(signal.symbol)
            logger.debug(
                "🚫 Ignorando señal %s | Ya hay trade %s (%s) para %s",
                signal.id, existing.id if existing else "?",
                existing.status.value if existing else "?", signal.symbol,
            )
            self._stats.signals_ignored += 1
            return None

        trade = SimulatedTrade(
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            signal_id=signal.id,
            signal_entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            rr=signal.rr,
            conditions=signal.conditions,
            max_duration_seconds=self._max_duration_seconds,
        )

        registered = self._state.register_trade(trade)
        if not registered:
            logger.warning(
                "⚠️ Race condition: trade no registrado para %s", signal.symbol,
            )
            return None

        self._stats.trades_opened += 1
        logger.info(
            "📝 Trade PENDING | id=%s sym=%s type=%s SL=%.5f TP=%.5f RR=%.2f",
            trade.id, trade.symbol, trade.signal_type,
            trade.stop_loss, trade.take_profit, trade.rr,
        )

        return trade

    # ════════════════════════════════════════════════════════════════
    #  2. EVALUAR TICK (PENDING → OPEN, OPEN → cerrado)
    # ════════════════════════════════════════════════════════════════

    def evaluate_tick(self, symbol: str, price: float, timestamp: float) -> SimulatedTrade | None:
        """
        Evalúa un tick contra el trade activo del símbolo.

        Flujo O(1):
          - Si trade PENDING → activar a precio actual
          - Si trade OPEN → evaluar TP, SL, Expiración
          - Si no hay trade → return None

        Returns:
            SimulatedTrade si se cerró un trade (para broadcast), None en caso contrario.

        NOTA SOBRE EVALUACIÓN TP/SL:
            BUY: Gana si price ≥ TP, pierde si price ≤ SL
            SELL: Gana si price ≤ TP, pierde si price ≥ SL

            Se evalúa SL ANTES que TP (conservador: ante duda, pierde).
            Esto previene sesgo optimista en escenarios de gap/spike.
        """
        trade = self._state.get_active_trade(symbol)
        if trade is None:
            return None

        # ── PENDING → OPEN (primer tick post-señal) ──
        if trade.is_pending:
            trade.activate(entry_price=price, timestamp=timestamp)
            logger.info(
                "🟢 Trade OPEN | id=%s sym=%s entry=%.5f (signal_entry=%.5f slippage=%.5f)",
                trade.id, trade.symbol, price,
                trade.signal_entry, abs(price - trade.signal_entry),
            )
            return None  # No cerrado aún, no hay broadcast de cierre

        # ── OPEN → Evaluar cierre ──
        assert trade.is_open

        # (a) Expiración temporal
        elapsed = timestamp - trade.open_timestamp
        if elapsed >= trade.max_duration_seconds:
            trade.close(
                close_price=price,
                status=TradeStatus.EXPIRED,
                timestamp=timestamp,
            )
            self._state.archive_trade(trade)
            self._stats.record_close(trade)
            self._notify_stats(trade)
            logger.info(
                "⏰ Trade EXPIRED | id=%s sym=%s entry=%.5f close=%.5f pnl=%.4f%% dur=%.0fs",
                trade.id, trade.symbol, trade.entry_price, price,
                trade.pnl_percent, trade.duration_seconds,
            )
            return trade

        # (b) Stop Loss (se evalúa ANTES que TP – conservador)
        if trade.signal_type == "BUY" and price <= trade.stop_loss:
            trade.close(close_price=price, status=TradeStatus.LOSS, timestamp=timestamp)
            self._state.archive_trade(trade)
            self._stats.record_close(trade)
            self._notify_stats(trade)
            logger.info(
                "🔴 Trade LOSS (SL) | id=%s sym=%s entry=%.5f close=%.5f pnl=%.4f%% dur=%.0fs",
                trade.id, trade.symbol, trade.entry_price, price,
                trade.pnl_percent, trade.duration_seconds,
            )
            return trade

        if trade.signal_type == "SELL" and price >= trade.stop_loss:
            trade.close(close_price=price, status=TradeStatus.LOSS, timestamp=timestamp)
            self._state.archive_trade(trade)
            self._stats.record_close(trade)
            self._notify_stats(trade)
            logger.info(
                "🔴 Trade LOSS (SL) | id=%s sym=%s entry=%.5f close=%.5f pnl=%.4f%% dur=%.0fs",
                trade.id, trade.symbol, trade.entry_price, price,
                trade.pnl_percent, trade.duration_seconds,
            )
            return trade

        # (c) Take Profit
        if trade.signal_type == "BUY" and price >= trade.take_profit:
            trade.close(close_price=price, status=TradeStatus.PROFIT, timestamp=timestamp)
            self._state.archive_trade(trade)
            self._stats.record_close(trade)
            self._notify_stats(trade)
            logger.info(
                "🟢 Trade PROFIT (TP) | id=%s sym=%s entry=%.5f close=%.5f pnl=+%.4f%% dur=%.0fs",
                trade.id, trade.symbol, trade.entry_price, price,
                trade.pnl_percent, trade.duration_seconds,
            )
            return trade

        if trade.signal_type == "SELL" and price <= trade.take_profit:
            trade.close(close_price=price, status=TradeStatus.PROFIT, timestamp=timestamp)
            self._state.archive_trade(trade)
            self._stats.record_close(trade)
            self._notify_stats(trade)
            logger.info(
                "🟢 Trade PROFIT (TP) | id=%s sym=%s entry=%.5f close=%.5f pnl=+%.4f%% dur=%.0fs",
                trade.id, trade.symbol, trade.entry_price, price,
                trade.pnl_percent, trade.duration_seconds,
            )
            return trade

        # Trade sigue abierto
        return None

    # ════════════════════════════════════════════════════════════════
    #  PROPIEDADES
    # ════════════════════════════════════════════════════════════════

    @property
    def stats(self) -> dict:
        """Estadísticas combinadas del simulador + state."""
        sim_stats = self._stats.to_dict()
        state_stats = self._state.stats
        return {**state_stats, **sim_stats}

    def _notify_stats(self, trade: SimulatedTrade) -> None:
        """Notificar al StatsEngine que un trade se cerró (invalida cache)."""
        if self._stats_engine is not None:
            self._stats_engine.on_trade_closed(trade)


# ════════════════════════════════════════════════════════════════════
#  STATS INTERNAS DEL SIMULADOR
# ════════════════════════════════════════════════════════════════════

class _SimulatorStats:
    """Contadores internos del simulador (no persistidos)."""

    __slots__ = (
        "trades_opened", "signals_ignored",
        "profit_count", "loss_count", "expired_count",
    )

    def __init__(self) -> None:
        self.trades_opened: int = 0
        self.signals_ignored: int = 0
        self.profit_count: int = 0
        self.loss_count: int = 0
        self.expired_count: int = 0

    def record_close(self, trade: SimulatedTrade) -> None:
        if trade.status == TradeStatus.PROFIT:
            self.profit_count += 1
        elif trade.status == TradeStatus.LOSS:
            self.loss_count += 1
        elif trade.status == TradeStatus.EXPIRED:
            self.expired_count += 1

    def to_dict(self) -> dict:
        return {
            "simulator_trades_opened": self.trades_opened,
            "simulator_signals_ignored": self.signals_ignored,
        }
