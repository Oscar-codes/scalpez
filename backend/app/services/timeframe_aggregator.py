"""
QuantPulse – Timeframe Aggregator
===================================
Agrega velas base (5s) en velas de timeframes superiores (5m, 15m, 30m, 1h).

ALGORITMO:
  1. Recibe cada vela base cerrada (5s).
  2. Para cada timeframe configurado, mantiene una vela "en construcción".
  3. Si la vela base cae dentro del intervalo del TF → actualiza OHLC.
  4. Si cruza el límite del intervalo → cierra la vela del TF y abre nueva.

ALINEACIÓN TEMPORAL:
  Las velas de TF superior se alinean a múltiplos exactos del intervalo:
    - 5m  (300s) → 00:00, 00:05, 00:10, ...
    - 15m (900s) → 00:00, 00:15, 00:30, ...
    - 30m (1800s) → 00:00, 00:30, 01:00, ...
    - 1h  (3600s) → 00:00, 01:00, 02:00, ...

PROTECCIÓN DE MEMORIA:
  Solo se mantiene UNA vela en construcción por (símbolo, timeframe).
  El almacenamiento histórico lo maneja MarketStateManager.

COMPLEJIDAD: O(T) por vela base, donde T = número de timeframes (4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from backend.app.core.logging import get_logger
from backend.app.domain.entities.candle import Candle

logger = get_logger("timeframe_aggregator")

# Mapeo de nombre de TF a segundos
TIMEFRAME_SECONDS: Dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


@dataclass
class _BuildingTFCandle:
    """Vela mutable en construcción para un timeframe superior."""

    symbol: str
    timeframe: str
    open_time: float
    close_time: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    tick_count: int = 0  # velas base agregadas

    def update_from_candle(self, candle: Candle) -> None:
        """Actualizar OHLC con una vela base cerrada."""
        if self.tick_count == 0:
            self.open = candle.open
            self.high = candle.high
            self.low = candle.low
        else:
            self.high = max(self.high, candle.high)
            self.low = min(self.low, candle.low)
        self.close = candle.close
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


class TimeframeAggregator:
    """
    Agrega velas base en velas de timeframes superiores.

    Uso:
        aggregator = TimeframeAggregator(["5m", "15m", "30m", "1h"])
        closed_list = aggregator.process_candle(base_candle)
        # closed_list = [(timeframe, Candle), ...] para cada TF que cerró
    """

    def __init__(self, timeframes: List[str]) -> None:
        self._timeframes = []
        self._intervals: Dict[str, int] = {}

        for tf in timeframes:
            if tf not in TIMEFRAME_SECONDS:
                logger.warning("Timeframe '%s' no reconocido, ignorado", tf)
                continue
            self._timeframes.append(tf)
            self._intervals[tf] = TIMEFRAME_SECONDS[tf]

        # (symbol, timeframe) → vela en construcción
        self._building: Dict[Tuple[str, str], _BuildingTFCandle] = {}

        logger.info(
            "TimeframeAggregator inicializado: %s",
            ", ".join(f"{tf}={self._intervals[tf]}s" for tf in self._timeframes),
        )

    @property
    def timeframes(self) -> List[str]:
        return list(self._timeframes)

    def _align_time(self, epoch: float, interval: int) -> float:
        """Alinear timestamp al inicio del intervalo."""
        return math.floor(epoch / interval) * interval

    def process_candle(self, candle: Candle) -> List[Tuple[str, Candle]]:
        """
        Procesar una vela base cerrada. Para cada timeframe:
          - Si cae dentro del intervalo actual → actualizar
          - Si cruza el límite → cerrar vela del TF y abrir nueva

        Returns:
            Lista de (timeframe, Candle) para cada TF que cerró una vela.
        """
        closed: List[Tuple[str, Candle]] = []
        symbol = candle.symbol
        candle_ts = candle.timestamp

        for tf in self._timeframes:
            interval = self._intervals[tf]
            key = (symbol, tf)
            building = self._building.get(key)

            if building is None:
                # Primera vela → abrir nueva
                open_time = self._align_time(candle_ts, interval)
                building = _BuildingTFCandle(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=open_time,
                    close_time=open_time + interval,
                )
                building.update_from_candle(candle)
                self._building[key] = building
                continue

            if candle_ts < building.close_time:
                # Vela base cae dentro del intervalo → actualizar
                building.update_from_candle(candle)
            else:
                # Cruzó el límite → cerrar y abrir nueva
                closed_candle = building.freeze()
                closed.append((tf, closed_candle))

                logger.debug(
                    "Vela %s cerrada [%s] O=%.5f H=%.5f L=%.5f C=%.5f base_candles=%d",
                    tf, symbol,
                    closed_candle.open, closed_candle.high,
                    closed_candle.low, closed_candle.close,
                    closed_candle.tick_count,
                )

                # Abrir nueva vela alineada
                new_open = self._align_time(candle_ts, interval)
                new_building = _BuildingTFCandle(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=new_open,
                    close_time=new_open + interval,
                )
                new_building.update_from_candle(candle)
                self._building[key] = new_building

        return closed

    def get_building_candle(
        self, symbol: str, timeframe: str,
    ) -> Optional[dict]:
        """Obtener vela en construcción (para mostrar en gráfico en tiempo real)."""
        key = (symbol, timeframe)
        building = self._building.get(key)
        if building is None or building.tick_count == 0:
            return None
        return {
            "symbol": building.symbol,
            "timeframe": building.timeframe,
            "timestamp": building.open_time,
            "open": building.open,
            "high": building.high,
            "low": building.low,
            "close": building.close,
            "tick_count": building.tick_count,
            "interval": int(building.close_time - building.open_time),
            "is_building": True,
        }
