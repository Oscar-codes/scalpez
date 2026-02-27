"""
QuantPulse – Process Tick Use Case
====================================
Caso de uso central: consume ticks del EventBus, construye velas,
actualiza MarketState, alimenta Indicadores, S/R y Signal Engine.

FLUJO:
  EventBus (tick topic)
       │
       ▼
  ProcessTickUseCase.run()  ◄── loop infinito consumiendo de su Queue
       │
       ├── MarketState.update_tick(tick)      → guardar último precio
       ├── CandleBuilder.process_tick(tick)   → construir vela
       │       │
       │       └── Si vela cerrada:
       │               ├── MarketState.add_candle(candle)
       │               ├── IndicatorService.update(candle)     → EMA 9/21, RSI 14
       │               ├── SupportResistanceService.update()   → swings S/R
       │               ├── SignalEngine.evaluate()             → BUY/SELL/None
       │               └── EventBus.publish("candle"|"signal")
       │
       └── EventBus.publish("tick_processed", tick)  → para WS broadcast

CÓMO SE EVITA PÉRDIDA DE TICKS:
- El UseCase consume de su cola exclusiva (provista por EventBus).
- El loop no tiene sleeps innecesarios: espera solo en queue.get().
- Cada tick se procesa atómicamente en operaciones O(1).

CÓMO SE EVITA REPAINTING:
- Solo las velas CERRADAS se publican en "candle" topic.
- Solo las velas CERRADAS alimentan al IndicatorService.
- La vela en construcción permanece privada en CandleBuilder.

ESCALABILIDAD:
- Se puede tener múltiples instances de este UseCase por partición de símbolos.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from backend.app.core.logging import get_logger
from backend.app.domain.entities.value_objects.tick import Tick
from backend.app.infrastructure.event_bus import EventBus
from backend.app.services.candle_builder import CandleBuilder
from backend.app.services.indicator_service import IndicatorService
from backend.app.services.signal_engine import SignalEngine
from backend.app.services.support_resistance_service import SupportResistanceService
from backend.app.services.timeframe_aggregator import TimeframeAggregator, TIMEFRAME_SECONDS
from backend.app.services.trade_simulator import TradeSimulator
from backend.app.state.market_state import MarketStateManager

logger = get_logger("process_tick")

# Tópicos del EventBus
TICK_TOPIC = "tick"
CANDLE_TOPIC = "candle"
TF_CANDLE_TOPIC = "tf_candle"           # vela de TF superior cerrada
TF_INDICATORS_TOPIC = "tf_indicators"   # indicadores de TF superior
TICK_PROCESSED_TOPIC = "tick_processed"
INDICATORS_TOPIC = "indicators_updated"
SIGNAL_TOPIC = "signal"
TRADE_OPENED_TOPIC = "trade_opened"
TRADE_CLOSED_TOPIC = "trade_closed"


class ProcessTickUseCase:
    """
    Consume ticks, construye velas base (5s), agrega en TFs superiores,
    actualiza estado, indicadores, S/R y genera señales.
    """

    def __init__(
        self,
        event_bus: EventBus,
        candle_builder: CandleBuilder,
        market_state: MarketStateManager,
        indicator_service: Optional[IndicatorService] = None,
        sr_service: Optional[SupportResistanceService] = None,
        signal_engine: Optional[SignalEngine] = None,
        trade_simulator: Optional[TradeSimulator] = None,
        tf_aggregator: Optional[TimeframeAggregator] = None,
        active_timeframe: str = "5m",
    ) -> None:
        self._event_bus = event_bus
        self._candle_builder = candle_builder
        self._market_state = market_state
        self._indicator_service = indicator_service
        self._sr_service = sr_service
        self._signal_engine = signal_engine
        self._trade_simulator = trade_simulator
        self._tf_aggregator = tf_aggregator
        self._active_timeframe = active_timeframe
        self._queue: asyncio.Queue | None = None
        self._running = False
        self._processed_count = 0

    @property
    def active_timeframe(self) -> str:
        return self._active_timeframe

    @active_timeframe.setter
    def active_timeframe(self, tf: str) -> None:
        if tf in TIMEFRAME_SECONDS:
            logger.info("Timeframe activo cambiado: %s → %s", self._active_timeframe, tf)
            self._active_timeframe = tf

    async def start(self) -> None:
        """Suscribirse al EventBus y lanzar loop de procesamiento."""
        self._queue = await self._event_bus.subscribe(TICK_TOPIC, "process_tick_usecase")
        self._running = True
        logger.info("ProcessTickUseCase iniciado, consumiendo tópico '%s'", TICK_TOPIC)
        await self._run()

    async def stop(self) -> None:
        """Detener procesamiento."""
        self._running = False
        logger.info(
            "ProcessTickUseCase detenido. Ticks procesados: %d", self._processed_count
        )

    async def _run(self) -> None:
        """
        Loop principal de consumo de ticks.
        Espera en queue.get() → no consume CPU cuando no hay datos.

        FLUJO MULTI-TIMEFRAME:
          tick → CandleBuilder (5s) → vela base
                  → TimeframeAggregator → velas TF superiores (5m/15m/30m/1h)
                      → Para CADA TF cerrada:
                          MarketState.add_tf_candle()
                          IndicatorService.update(candle, tf)
                          EventBus.publish(tf_candle/tf_indicators)
                      → Solo para TF ACTIVO:
                          SRService.update()
                          SignalEngine.evaluate()
        """
        assert self._queue is not None

        while self._running:
            try:
                # Esperar tick con timeout para permitir shutdown limpio
                try:
                    tick: Tick = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # ── 1. Actualizar estado de mercado ──
                self._market_state.update_tick(tick)

                # ── 1b. Evaluar trade activo en CADA tick ──
                if self._trade_simulator is not None:
                    closed_trade = self._trade_simulator.evaluate_tick(
                        symbol=tick.symbol,
                        price=tick.quote,
                        timestamp=tick.epoch,
                    )
                    if closed_trade is not None:
                        await self._event_bus.publish(
                            TRADE_CLOSED_TOPIC, closed_trade
                        )

                # ── 2. Alimentar CandleBuilder (velas base 5s) ──
                closed_candle = self._candle_builder.process_tick(tick)

                if closed_candle is not None:
                    # Vela base cerrada → guardar + publicar
                    self._market_state.add_candle(closed_candle)
                    await self._event_bus.publish(CANDLE_TOPIC, closed_candle)

                    # ── 3. Agregar en timeframes superiores ──────────
                    if self._tf_aggregator is not None:
                        tf_closed_list = self._tf_aggregator.process_candle(
                            closed_candle
                        )

                        for tf, tf_candle in tf_closed_list:
                            await self._process_tf_candle(tf, tf_candle)

                # ── 7. Notificar tick procesado (para WS broadcast) ──
                await self._event_bus.publish(TICK_PROCESSED_TOPIC, tick)

                self._processed_count += 1

            except asyncio.CancelledError:
                logger.info("ProcessTickUseCase cancelado")
                break
            except Exception as e:
                logger.error("Error procesando tick: %s", e, exc_info=True)
                continue

    async def _process_tf_candle(self, timeframe: str, candle) -> None:
        """
        Procesar una vela cerrada de un timeframe superior.

        Para TODOS los TFs: almacenar + indicadores.
        Solo para el TF ACTIVO: S/R + señales + trades.
        """
        symbol = candle.symbol

        # ── Almacenar vela en MarketState ──
        self._market_state.add_tf_candle(candle, timeframe)

        # ── Publicar vela cerrada del TF ──
        candle_data = candle.to_dict()
        candle_data["timeframe"] = timeframe
        await self._event_bus.publish(TF_CANDLE_TOPIC, candle_data)

        # ── Indicadores para este TF ──
        indicator_result = None
        if self._indicator_service is not None:
            indicator_result = self._indicator_service.update(candle, timeframe)

            if indicator_result is not None:
                indicator_result["timeframe"] = timeframe
                # Asegurar symbol limpio
                if ":" in indicator_result.get("symbol", ""):
                    indicator_result["symbol"] = symbol
                await self._event_bus.publish(TF_INDICATORS_TOPIC, indicator_result)

                logger.info(
                    "Vela+Ind %s [%s] C=%.5f EMA9=%.5f EMA21=%.5f RSI=%.2f",
                    timeframe, symbol,
                    candle.close,
                    indicator_result.get("ema_9") or 0,
                    indicator_result.get("ema_21") or 0,
                    indicator_result.get("rsi_14") or 0,
                )

        # ── Solo el TF activo genera señales y actualiza S/R ──
        if timeframe != self._active_timeframe:
            return

        # ── S/R para TF activo ──
        candles_buf = self._market_state.get_or_create(symbol).get_tf_candles(
            timeframe
        )
        if self._sr_service is not None:
            self._sr_service.update(candle, candles_buf)

        # ── Señales solo para TF activo ──
        if self._signal_engine is not None and indicator_result is not None:
            signal = self._signal_engine.evaluate(
                candle, indicator_result, candles_buf,
            )
            if signal is not None:
                await self._event_bus.publish(SIGNAL_TOPIC, signal)

                # ── Trade simulado ──
                if self._trade_simulator is not None:
                    new_trade = self._trade_simulator.open_trade(signal)
                    if new_trade is not None:
                        await self._event_bus.publish(
                            TRADE_OPENED_TOPIC, new_trade
                        )
