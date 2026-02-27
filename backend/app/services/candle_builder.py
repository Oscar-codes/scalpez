"""
QuantPulse – Candle Builder Service
=====================================
Construye velas OHLC a partir de ticks en tiempo real.

ALGORITMO:
  1. El primer tick de un intervalo abre una nueva vela temporal (mutable).
  2. Cada tick actualiza high/low/close de la vela temporal.
  3. Cuando llega un tick cuyo epoch supera el cierre del intervalo,
     la vela se "cierra": se congela como Candle inmutable y se retorna.

CÓMO SE EVITA REPAINTING:
- La vela temporal solo existe en `_building`. Solo cuando .close_time es
  superado se convierte en Candle(frozen=True) y se entrega al consumer.
- Una vez congelada, NADIE puede modificarla.
- Los consumidores solo reciben velas cerradas para decisiones de señal.

CÓMO SE EVITA PÉRDIDA DE TICKS:
- process_tick() es O(1) — solo comparaciones y asignaciones.
- No hay I/O, no hay await, no hay bloqueo.

PROTECCIÓN DE MEMORIA:
- Solo se mantiene UNA vela en construcción por símbolo.
- El almacenamiento histórico lo maneja MarketStateManager con deque(maxlen).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

from backend.app.core.logging import get_logger
from backend.app.core.settings import settings
from backend.app.domain.entities.candle import Candle
from backend.app.domain.entities.value_objects.tick import Tick

logger = get_logger("candle_builder")


@dataclass
class _BuildingCandle:
    """Vela mutable en construcción (solo uso interno)."""

    symbol: str
    open_time: float      # epoch de apertura (alineado al intervalo)
    close_time: float     # epoch de cierre esperado
    open: float = 0.0
    high: float = -math.inf
    low: float = math.inf
    close: float = 0.0
    tick_count: int = 0

    def update(self, price: float) -> None:
        """Actualizar OHLC con un nuevo precio."""
        if self.tick_count == 0:
            self.open = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.tick_count += 1

    def freeze(self) -> Candle:
        """Convertir en Candle inmutable."""
        return Candle(
            symbol=self.symbol,
            timestamp=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            tick_count=self.tick_count,
            interval=int(self.close_time - self.open_time),
        )


class CandleBuilder:
    """
    Construye velas OHLC por símbolo a partir de ticks.

    Uso:
        builder = CandleBuilder(interval=5)
        closed = builder.process_tick(tick)
        if closed:
            # vela completada → enviar a MarketState, indicadores, etc.
    """

    def __init__(self, interval: int | None = None) -> None:
        self._interval = interval or settings.candle_interval_seconds
        # symbol → vela en construcción
        self._building: Dict[str, _BuildingCandle] = {}
        logger.info("CandleBuilder inicializado (intervalo=%ds)", self._interval)

    def _align_time(self, epoch: float) -> float:
        """Alinear un timestamp al inicio del intervalo más cercano."""
        return math.floor(epoch / self._interval) * self._interval

    def process_tick(self, tick: Tick) -> Optional[Candle]:
        """
        Procesar un tick. Retorna Candle si la vela se cerró, None si no.

        Operación O(1) – sin I/O, sin bloqueo.
        """
        symbol = tick.symbol
        epoch = tick.epoch
        price = tick.quote

        building = self._building.get(symbol)

        # ── CASO 1: No hay vela en construcción → abrir una nueva ──
        if building is None:
            open_time = self._align_time(epoch)
            building = _BuildingCandle(
                symbol=symbol,
                open_time=open_time,
                close_time=open_time + self._interval,
            )
            building.update(price)
            self._building[symbol] = building
            return None

        # ── CASO 2: Tick pertenece a la vela actual ──
        if epoch < building.close_time:
            building.update(price)
            return None

        # ── CASO 3: Tick cae fuera del intervalo → cerrar vela, abrir nueva ──
        closed_candle = building.freeze()

        # Abrir nueva vela alineada al epoch del tick actual
        new_open = self._align_time(epoch)
        new_building = _BuildingCandle(
            symbol=symbol,
            open_time=new_open,
            close_time=new_open + self._interval,
        )
        new_building.update(price)
        self._building[symbol] = new_building

        logger.debug(
            "Vela cerrada: %s O=%.5f H=%.5f L=%.5f C=%.5f ticks=%d",
            closed_candle.symbol,
            closed_candle.open,
            closed_candle.high,
            closed_candle.low,
            closed_candle.close,
            closed_candle.tick_count,
        )

        return closed_candle

    def get_building_candle(self, symbol: str) -> Optional[dict]:
        """Obtener la vela en construcción (para preview en frontend)."""
        building = self._building.get(symbol)
        if building is None or building.tick_count == 0:
            return None
        return {
            "symbol": building.symbol,
            "timestamp": building.open_time,
            "open": building.open,
            "high": building.high,
            "low": building.low,
            "close": building.close,
            "tick_count": building.tick_count,
            "is_building": True,
        }
