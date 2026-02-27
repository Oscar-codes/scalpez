"""
QuantPulse – Main Application Entry Point
============================================
Orquesta todos los componentes: Market Stream Engine + Indicator Engine.

ARQUITECTURA DE ARRANQUE:
  1. Configurar logging
  2. Crear instancias (Event Bus, Market State, Indicator State, etc.)
  3. FastAPI startup event:
     a. Iniciar DerivClient (conexión WS a Deriv)
     b. Iniciar ProcessTickUseCase (consumer de ticks + indicadores)
     c. Iniciar WebSocketManager (broadcast a frontend)
  4. FastAPI shutdown event:
     a. Detener todo en orden inverso

FLUJO DE DATOS:
  Deriv WS → DerivClient → EventBus(tick) → ProcessTickUseCase
       → CandleBuilder → MarketState
       → IndicatorService → IndicatorState (EMA 9/21, RSI 14)
       → EventBus(tick_processed) → WebSocketManager → Frontend WS
       → EventBus(candle) → WebSocketManager → Frontend WS
       → EventBus(indicators_updated) → WebSocketManager → Frontend WS

EJECUCIÓN:
  cd backend
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.logging import setup_logging, get_logger
from backend.app.core.settings import settings
from backend.app.infrastructure.event_bus import EventBus
from backend.app.infrastructure.deriv_client import DerivClient
from backend.app.services.candle_builder import CandleBuilder
from backend.app.services.indicator_service import IndicatorService
from backend.app.state.market_state import MarketStateManager
from backend.app.state.indicator_state import IndicatorStateManager
from backend.app.application.process_tick_usecase import ProcessTickUseCase
from backend.app.api.websocket_manager import WebSocketManager
from backend.app.api.routes import router, init_routes

# ─── Logging ────────────────────────────────────────────────────────────
setup_logging()
logger = get_logger("main")

# ─── Instancias globales (composición en el root) ──────────────────────
event_bus = EventBus(max_queue_size=settings.event_bus_max_queue_size)
market_state = MarketStateManager()
indicator_state = IndicatorStateManager()
candle_builder = CandleBuilder(interval=settings.candle_interval_seconds)
indicator_service = IndicatorService(state_manager=indicator_state)
deriv_client = DerivClient(event_bus=event_bus)
process_tick = ProcessTickUseCase(
    event_bus=event_bus,
    candle_builder=candle_builder,
    market_state=market_state,
    indicator_service=indicator_service,
)
ws_manager = WebSocketManager(event_bus=event_bus)

# Task references para lifecycle
_background_tasks: list[asyncio.Task] = []


# ─── FastAPI Lifespan ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown lifecycle de la aplicación.
    Todas las coroutines de larga duración se lanzan como tasks.
    """
    logger.info("=" * 60)
    logger.info("  QuantPulse – Market Stream Engine + Indicator Engine v0.2")
    logger.info("  Símbolos: %s", ", ".join(settings.deriv_symbols))
    logger.info("  Intervalo velas: %ds", settings.candle_interval_seconds)
    logger.info("  Buffer máximo: %d velas por símbolo", settings.max_candles_buffer)
    logger.info("  Indicadores: EMA 9, EMA 21, RSI 14 (incremental O(1))")
    logger.info("=" * 60)

    # Inyectar dependencias al router
    init_routes(ws_manager, market_state, deriv_client, indicator_service)

    # Iniciar WebSocket Manager (broadcast loops)
    await ws_manager.start()

    # Iniciar ProcessTickUseCase como background task
    tick_task = asyncio.create_task(
        process_tick.start(), name="process-tick-usecase"
    )
    _background_tasks.append(tick_task)

    # Iniciar DerivClient (conexión a Deriv)
    await deriv_client.start()

    logger.info("✓ Todos los componentes iniciados correctamente")

    yield  # ← La app está corriendo aquí

    # ── SHUTDOWN ──
    logger.info("Iniciando shutdown...")

    await deriv_client.stop()
    await process_tick.stop()
    await ws_manager.stop()

    # Cancelar background tasks
    for task in _background_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    await event_bus.unsubscribe_all()
    logger.info("✓ Shutdown completo")


# ─── FastAPI App ────────────────────────────────────────────────────────

app = FastAPI(
    title="QuantPulse – Market Stream + Indicator Engine",
    description="Motor de datos de mercado en tiempo real con indicadores para scalping",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS para frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: restringir a dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(router)
