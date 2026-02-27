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

from backend.shared.logging.logger import setup_logging, get_logger
from backend.shared.config.settings import settings
from backend.app.infrastructure.database import get_db_manager
from backend.presentation.api.routes import router, init_routes
from backend.container import get_container, init_container

# ─── Logging ────────────────────────────────────────────────────────────
setup_logging()
logger = get_logger("main")

# ─── Contenedor de Dependencias ─────────────────────────────────────────
# Todas las instancias se obtienen del container (DI)
container = init_container()

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

    # Inicializar base de datos (opcional)
    if settings.db_enabled:
        db_manager = get_db_manager()
        await db_manager.initialize()
        logger.info("  Database: MySQL conectada (%s@%s/%s)",
                    settings.db_user, settings.db_host, settings.db_name)
        
        # Iniciar PersistenceListener para guardar señales y trades
        from backend.infrastructure.persistence.persistence_listener import PersistenceListener
        persistence_listener = PersistenceListener(container.event_bus)
        await persistence_listener.start()
        container._persistence_listener = persistence_listener  # Guardar referencia
    else:
        logger.info("  Database: Deshabilitada (db_enabled=False)")

    # Inyectar dependencias al router (desde container)
    init_routes(
        container.ws_manager, container.market_state, container.deriv_client,
        container.indicator_service, container.signal_engine, container.sr_service,
        container.trade_simulator, container.trade_state, container.stats_engine,
        process_tick=container.legacy_process_tick,
        tf_aggregator=container.tf_aggregator,
    )

    # Iniciar WebSocket Manager (broadcast loops)
    await container.ws_manager.start()

    # Iniciar ProcessTickUseCase como background task
    tick_task = asyncio.create_task(
        container.legacy_process_tick.start(), name="process-tick-usecase"
    )
    _background_tasks.append(tick_task)

    # Iniciar DerivClient (conexión a Deriv)
    await container.deriv_client.start()

    logger.info("✓ Todos los componentes iniciados correctamente")

    yield  # ← La app está corriendo aquí

    # ── SHUTDOWN ──
    logger.info("Iniciando shutdown...")

    # Detener PersistenceListener
    if settings.db_enabled and hasattr(container, '_persistence_listener'):
        await container._persistence_listener.stop()
        logger.info("  PersistenceListener: Detenido")

    # Cerrar conexión a base de datos
    if settings.db_enabled:
        db_manager = get_db_manager()
        await db_manager.close()
        logger.info("  Database: Conexión cerrada")

    await container.deriv_client.stop()
    await container.legacy_process_tick.stop()
    await container.ws_manager.stop()

    # Cancelar background tasks
    for task in _background_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    await container.event_bus.unsubscribe_all()
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
