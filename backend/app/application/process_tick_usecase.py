"""
QuantPulse – Process Tick Use Case
====================================
Caso de uso central: consume ticks del EventBus, construye velas,
actualiza MarketState y alimenta el Indicator Engine.

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
       │               └── EventBus.publish("candle", candle)
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
from backend.app.state.market_state import MarketStateManager

logger = get_logger("process_tick")

# Tópicos del EventBus
TICK_TOPIC = "tick"
CANDLE_TOPIC = "candle"
TICK_PROCESSED_TOPIC = "tick_processed"
INDICATORS_TOPIC = "indicators_updated"


class ProcessTickUseCase:
    """Consume ticks, construye velas, actualiza estado e indicadores."""

    def __init__(
        self,
        event_bus: EventBus,
        candle_builder: CandleBuilder,
        market_state: MarketStateManager,
        indicator_service: Optional[IndicatorService] = None,
    ) -> None:
        self._event_bus = event_bus
        self._candle_builder = candle_builder
        self._market_state = market_state
        self._indicator_service = indicator_service
        self._queue: asyncio.Queue | None = None
        self._running = False
        self._processed_count = 0

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

                # ── 2. Alimentar CandleBuilder ──
                closed_candle = self._candle_builder.process_tick(tick)

                if closed_candle is not None:
                    # Vela cerrada → guardar en estado + publicar
                    self._market_state.add_candle(closed_candle)
                    await self._event_bus.publish(CANDLE_TOPIC, closed_candle)

                    # ── 3. Actualizar indicadores (Fase 2) ──
                    # Solo velas CERRADAS alimentan los indicadores → sin repainting.
                    # IndicatorService.update() es O(1) post warm-up.
                    if self._indicator_service is not None:
                        indicator_result = self._indicator_service.update(closed_candle)

                        if indicator_result is not None:
                            # Indicadores listos → publicar para WS broadcast
                            await self._event_bus.publish(
                                INDICATORS_TOPIC, indicator_result
                            )
                            logger.info(
                                "Vela+Ind [%s] C=%.5f EMA9=%.5f EMA21=%.5f RSI=%.2f",
                                closed_candle.symbol,
                                closed_candle.close,
                                indicator_result.get("ema_9") or 0,
                                indicator_result.get("ema_21") or 0,
                                indicator_result.get("rsi_14") or 0,
                            )
                        else:
                            logger.info(
                                "Vela [%s] O=%.5f C=%.5f ticks=%d (warm-up %d/%d)",
                                closed_candle.symbol,
                                closed_candle.open,
                                closed_candle.close,
                                closed_candle.tick_count,
                                self._indicator_service._state_manager.get_or_create(
                                    closed_candle.symbol
                                ).warmup_count,
                                21,  # MIN_WARMUP
                            )
                    else:
                        logger.info(
                            "Vela cerrada [%s] O=%.5f C=%.5f ticks=%d",
                            closed_candle.symbol,
                            closed_candle.open,
                            closed_candle.close,
                            closed_candle.tick_count,
                        )

                # ── 4. Notificar tick procesado (para WS broadcast) ──
                await self._event_bus.publish(TICK_PROCESSED_TOPIC, tick)

                self._processed_count += 1

            except asyncio.CancelledError:
                logger.info("ProcessTickUseCase cancelado")
                break
            except Exception as e:
                logger.error("Error procesando tick: %s", e, exc_info=True)
                # No re-raise: un tick malo no debe matar el loop
                continue
