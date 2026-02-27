"""
QuantPulse – Market State Manager
==================================
Estado en memoria por símbolo: buffer de velas, último tick, trade activo.

PROTECCIÓN DE MEMORIA:
- El buffer de velas usa collections.deque con maxlen → descarta automáticamente
  las velas más antiguas cuando se excede el límite. O(1) en append y pop.
- Nunca se almacenan más de `max_candles` velas por símbolo.

CÓMO SE EVITA REPAINTING:
- Las velas en el buffer son objetos frozen (inmutables).
- Solo la ´vela en construcción` (current_candle del CandleBuilder) es mutable;
  una vez cerrada se congela y se inserta aquí como Candle inmutable.

RACE CONDITIONS:
- Todas las operaciones se ejecutan dentro del mismo event loop asyncio.
- No hay threads → no hay race conditions para atributos simples.
- Para operaciones compuestas futuras se puede añadir asyncio.Lock si es necesario.

ESCALABILIDAD:
- Cada símbolo tiene su propio SymbolState.
- Fácil de particionar por símbolo si se escala a múltiples procesos.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional

from backend.app.core.logging import get_logger
from backend.app.core.settings import settings
from backend.app.domain.entities.candle import Candle
from backend.app.domain.entities.value_objects.tick import Tick

logger = get_logger("market_state")


@dataclass
class SymbolState:
    """Estado de mercado para UN símbolo."""

    symbol: str
    last_tick: Optional[Tick] = None
    last_price: float = 0.0
    # Velas base (5s) — se mantienen para el CandleBuilder original
    candles: deque = field(default_factory=lambda: deque(maxlen=settings.max_candles_buffer))

    # Velas por timeframe: { "5m": deque, "15m": deque, ... }
    tf_candles: Dict[str, deque] = field(default_factory=dict)

    # Placeholder para trade activo (Fase futura)
    active_trade: Optional[dict] = None

    # Contadores de monitoreo
    total_ticks: int = 0
    total_candles: int = 0

    def get_tf_candles(self, timeframe: str) -> deque:
        """Obtener buffer de velas de un timeframe, creando si no existe."""
        if timeframe not in self.tf_candles:
            self.tf_candles[timeframe] = deque(maxlen=settings.max_candles_buffer)
        return self.tf_candles[timeframe]


class MarketStateManager:
    """
    Gestor centralizado del estado de mercado para todos los símbolos.

    Soporta velas base (5s) y velas de múltiples timeframes.
    Acceso: market_state[symbol] → SymbolState
    """

    def __init__(self) -> None:
        self._states: Dict[str, SymbolState] = {}

    def get_or_create(self, symbol: str) -> SymbolState:
        """Obtener estado de un símbolo; crearlo si no existe."""
        if symbol not in self._states:
            self._states[symbol] = SymbolState(symbol=symbol)
            logger.info("Estado creado para símbolo '%s' (max_candles=%d)",
                        symbol, settings.max_candles_buffer)
        return self._states[symbol]

    def update_tick(self, tick: Tick) -> None:
        """Actualizar último tick y precio de un símbolo."""
        state = self.get_or_create(tick.symbol)
        state.last_tick = tick
        state.last_price = tick.quote
        state.total_ticks += 1

    def add_candle(self, candle: Candle) -> None:
        """
        Añadir una vela base cerrada (5s) al buffer.
        deque(maxlen=N) descarta automáticamente la más antigua si se excede.
        """
        state = self.get_or_create(candle.symbol)
        state.candles.append(candle)
        state.total_candles += 1

    def add_tf_candle(self, candle: Candle, timeframe: str) -> None:
        """
        Añadir una vela cerrada de un timeframe superior.
        """
        state = self.get_or_create(candle.symbol)
        buf = state.get_tf_candles(timeframe)
        buf.append(candle)

    def get_candles(self, symbol: str, count: int | None = None) -> list[Candle]:
        """Obtener las últimas N velas base (5s) de un símbolo."""
        state = self.get_or_create(symbol)
        if count is None:
            return list(state.candles)
        return list(state.candles)[-count:]

    def get_tf_candles(
        self, symbol: str, timeframe: str, count: int | None = None,
    ) -> list[Candle]:
        """Obtener las últimas N velas de un timeframe de un símbolo."""
        state = self.get_or_create(symbol)
        buf = state.get_tf_candles(timeframe)
        if count is None:
            return list(buf)
        return list(buf)[-count:]

    def get_last_price(self, symbol: str) -> float:
        """Precio más reciente de un símbolo."""
        state = self.get_or_create(symbol)
        return state.last_price

    def get_all_symbols(self) -> list[str]:
        """Todos los símbolos con estado activo."""
        return list(self._states.keys())

    def snapshot(self) -> dict:
        """Snapshot completo para diagnóstico / API."""
        result = {}
        for symbol, s in self._states.items():
            tf_info = {
                tf: len(buf) for tf, buf in s.tf_candles.items()
            }
            result[symbol] = {
                "last_price": s.last_price,
                "total_ticks": s.total_ticks,
                "total_candles": s.total_candles,
                "candles_in_buffer": len(s.candles),
                "tf_candles": tf_info,
                "has_active_trade": s.active_trade is not None,
            }
        return result
