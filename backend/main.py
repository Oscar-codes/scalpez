"""
QuantPulse – Main Application Entry Point
============================================
Orquesta todos los componentes: Market Stream + Indicators + Signal Engine + Trade Simulator + Stats Engine.

ARQUITECTURA DE ARRANQUE:
  1. Configurar logging
  2. Crear instancias (Event Bus, Market State, Indicator State, S/R, Trade, etc.)
  3. FastAPI startup event:
     a. Iniciar DerivClient (conexión WS a Deriv)
     b. Iniciar ProcessTickUseCase (consumer de ticks + indicadores + señales + trades)
     c. Iniciar WebSocketManager (broadcast a frontend)
  4. FastAPI shutdown event:
     a. Detener todo en orden inverso

FLUJO DE DATOS:
  Deriv WS → DerivClient → EventBus(tick) → ProcessTickUseCase
       → CandleBuilder → MarketState
       → IndicatorService → IndicatorState (EMA 9/21, RSI 14)
       → SupportResistanceService → Swing Highs/Lows dinámicos
       → SignalEngine → Signal (BUY/SELL multi-confirmación)
       → TradeSimulator → SimulatedTrade (paper trading)
       → StatsEngine → PerformanceMetrics (12 metricas cuantitativas)
       → EventBus(trade_opened|trade_closed) → WebSocketManager → Frontend
  uvicorn main:app --reload --host 0.0.0.0 --port 8888
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.core.logging import setup_logging, get_logger
from backend.app.core.settings import settings
from backend.app.infrastructure.event_bus import EventBus
from backend.app.infrastructure.deriv_client import DerivClient
from backend.app.services.candle_builder import CandleBuilder
from backend.app.services.indicator_service import IndicatorService
from backend.app.services.support_resistance_service import SupportResistanceService
from backend.app.services.signal_engine import SignalEngine
from backend.app.services.trade_simulator import TradeSimulator
from backend.app.services.stats_engine import StatsEngine
from backend.app.services.timeframe_aggregator import TimeframeAggregator
from backend.app.state.market_state import MarketStateManager
from backend.app.state.indicator_state import IndicatorStateManager
from backend.app.state.trade_state import TradeStateManager
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
sr_service = SupportResistanceService(
    max_levels=settings.signal_sr_max_levels,
    sr_tolerance_pct=settings.signal_sr_tolerance_pct,
    breakout_candle_mult=settings.signal_breakout_candle_mult,
    consolidation_candles=settings.signal_consolidation_candles,
    consolidation_atr_mult=settings.signal_consolidation_atr_mult,
)
signal_engine = SignalEngine(
    sr_service=sr_service,
    min_confirmations=settings.signal_min_confirmations,
    rr_ratio=settings.signal_rr_ratio,
    min_rr=settings.signal_min_rr,
    rsi_oversold=settings.signal_rsi_oversold,
    rsi_overbought=settings.signal_rsi_overbought,
    min_sl_pct=settings.signal_min_sl_pct,
    cooldown_candles=settings.signal_cooldown_candles,
    candle_interval=settings.candle_interval_seconds,
)
trade_state = TradeStateManager()
stats_engine = StatsEngine(trade_state=trade_state)
trade_simulator = TradeSimulator(trade_state=trade_state, stats_engine=stats_engine)
tf_aggregator = TimeframeAggregator(timeframes=settings.available_timeframes)
deriv_client = DerivClient(event_bus=event_bus)
process_tick = ProcessTickUseCase(
    event_bus=event_bus,
    candle_builder=candle_builder,
    market_state=market_state,
    indicator_service=indicator_service,
    sr_service=sr_service,
    signal_engine=signal_engine,
    trade_simulator=trade_simulator,
    tf_aggregator=tf_aggregator,
    active_timeframe=settings.default_timeframe,
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
    logger.info("  QuantPulse - Multi-Timeframe v0.8")
    logger.info("  Símbolos: %s", ", ".join(settings.deriv_symbols))
    logger.info("  Vela base: %ds", settings.candle_interval_seconds)
    logger.info("  Timeframes: %s  (activo: %s)",
                ", ".join(settings.available_timeframes),
                settings.default_timeframe)
    logger.info("  Buffer máximo: %d velas por símbolo por TF", settings.max_candles_buffer)
    logger.info("  Indicadores: EMA 9, EMA 21, RSI 14 (incremental O(1) por TF)")
    logger.info("  Señales: multi-confirmación (≥%d), RR=%.1f, min_RR=%.1f",
                settings.signal_min_confirmations,
                settings.signal_rr_ratio,
                settings.signal_min_rr)
    logger.info("  Paper Trading: max_duration=%d min, RR=%.1f",
                settings.max_trade_duration,
                settings.rr_default)
    logger.info("  Stats Engine: 12 metricas cuantitativas O(n), cache lazy")
    logger.info("=" * 60)

    # Inyectar dependencias al router
    init_routes(
        ws_manager, market_state, deriv_client,
        indicator_service, signal_engine, sr_service,
        trade_simulator, trade_state, stats_engine,
        process_tick=process_tick,
        tf_aggregator=tf_aggregator,
    )

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
    title="QuantPulse - Multi-Timeframe",
    description="Motor de performance analytics cuantitativo con multi-timeframe, paper trading y señales multi-confirmación",
    version="0.8.0",
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

# ─── Frontend (archivos estáticos) ──────────────────────────────────────
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/", include_in_schema=False)
async def serve_index():
    """Servir index.html en la raíz."""
    return FileResponse(_frontend_dir / "index.html")

# Montar directorio frontend como archivos estáticos
app.mount("/", StaticFiles(directory=str(_frontend_dir)), name="frontend")
