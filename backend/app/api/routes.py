"""
QuantPulse – API Routes (FastAPI)
===================================
Endpoints REST y WebSocket para el frontend.

Endpoints disponibles:
  WS   /ws/market              → streaming en tiempo real
  GET  /api/health             → health check
  GET  /api/status             → estado completo del sistema
  GET  /api/candles/{symbol}   → últimas N velas
  GET  /api/indicators/{symbol}→ indicadores actuales de un símbolo
  GET  /api/indicators         → indicadores de todos los símbolos
  GET  /api/signals/stats      → estadísticas del motor de señales
  GET  /api/signals/recent     → señales recientes
  GET  /api/sr/{symbol}        → niveles S/R de un símbolo
  GET  /api/sr                 → niveles S/R de todos los símbolos
  GET  /api/trades/active      → trades activos
  GET  /api/trades/history     → historial de trades cerrados
  GET  /api/trades/stats       -> estadisticas de paper trading
  GET  /api/stats              -> metricas cuantitativas globales + por simbolo
  GET  /api/stats/{symbol}     -> metricas cuantitativas de un simbolo
  GET  /api/timeframe          -> timeframe activo y disponibles
  POST /api/timeframe          -> cambiar timeframe activo
  GET  /api/candles/{symbol}/{timeframe} -> velas de un TF específico
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from backend.app.core.logging import get_logger
from backend.app.core.settings import settings

logger = get_logger("api.routes")

router = APIRouter()

# Referencias a componentes inyectados desde main.py
_ws_manager = None
_market_state = None
_deriv_client = None
_indicator_service = None
_signal_engine = None
_sr_service = None
_trade_simulator = None
_trade_state = None
_stats_engine = None
_process_tick = None
_tf_aggregator = None


class TimeframeRequest(BaseModel):
    """Body para cambiar timeframe activo."""
    timeframe: str


def init_routes(
    ws_manager,
    market_state,
    deriv_client,
    indicator_service=None,
    signal_engine=None,
    sr_service=None,
    trade_simulator=None,
    trade_state=None,
    stats_engine=None,
    process_tick=None,
    tf_aggregator=None,
) -> None:
    """Inyectar dependencias desde main.py al arrancar."""
    global _ws_manager, _market_state, _deriv_client
    global _indicator_service, _signal_engine, _sr_service
    global _trade_simulator, _trade_state, _stats_engine
    global _process_tick, _tf_aggregator
    _ws_manager = ws_manager
    _market_state = market_state
    _deriv_client = deriv_client
    _indicator_service = indicator_service
    _signal_engine = signal_engine
    _sr_service = sr_service
    _trade_simulator = trade_simulator
    _trade_state = trade_state
    _stats_engine = stats_engine
    _process_tick = process_tick
    _tf_aggregator = tf_aggregator


# ─── WebSocket endpoint para streaming a frontend ─────────────────────

@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint principal.
    El frontend se conecta aquí para recibir ticks, velas, indicadores
    y señales en tiempo real. El broadcast lo maneja WebSocketManager -
    este handler solo gestiona el ciclo de vida de la conexión.
    """
    if _ws_manager is None:
        await websocket.close(code=1011, reason="Server not ready")
        return

    await _ws_manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_text()
                logger.debug("Mensaje de cliente WS: %s", data[:100])
            except WebSocketDisconnect:
                break
    finally:
        _ws_manager.disconnect(websocket)


# ─── REST endpoints de estado ──────────────────────────────────────────

@router.get("/api/health")
async def health_check() -> dict:
    """Health check para monitoreo."""
    return {"status": "ok", "service": "quantpulse"}


@router.get("/api/status")
async def system_status() -> dict:
    """Estado completo del sistema incluyendo indicadores, señales y trades."""
    result = {
        "market_state": _market_state.snapshot() if _market_state else {},
        "deriv_client": _deriv_client.stats if _deriv_client else {},
        "ws_clients": _ws_manager.client_count if _ws_manager else 0,
        "indicators": _indicator_service.get_all_indicators() if _indicator_service else {},
        "signal_engine": _signal_engine.stats if _signal_engine else {},
        "trade_simulator": _trade_simulator.stats if _trade_simulator else {},
    }
    return result


@router.get("/api/candles/{symbol}")
async def get_candles(symbol: str, count: int = 50) -> dict:
    """Obtener últimas N velas base (5s) de un símbolo."""
    if _market_state is None:
        return {"error": "Server not ready", "candles": []}

    count = min(count, 200)
    candles = _market_state.get_candles(symbol, count)
    return {
        "symbol": symbol,
        "count": len(candles),
        "candles": [c.to_dict() for c in candles],
    }


@router.get("/api/candles/{symbol}/{timeframe}")
async def get_tf_candles(symbol: str, timeframe: str, count: int = 200) -> dict:
    """Obtener últimas N velas de un timeframe específico."""
    if _market_state is None:
        return {"error": "Server not ready", "candles": []}

    if timeframe not in settings.available_timeframes:
        return {
            "error": f"Timeframe '{timeframe}' no válido",
            "available": settings.available_timeframes,
        }

    count = min(count, 200)
    candles = _market_state.get_tf_candles(symbol, timeframe, count)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": [c.to_dict() for c in candles],
    }


# ─── REST endpoints de timeframe ──────────────────────────────────────

@router.get("/api/timeframe")
async def get_timeframe() -> dict:
    """Obtener timeframe activo y disponibles."""
    active = _process_tick.active_timeframe if _process_tick else settings.default_timeframe
    return {
        "active": active,
        "available": settings.available_timeframes,
    }


@router.post("/api/timeframe")
async def set_timeframe(body: TimeframeRequest) -> dict:
    """Cambiar el timeframe activo para generación de señales."""
    tf = body.timeframe
    if tf not in settings.available_timeframes:
        return {
            "error": f"Timeframe '{tf}' no válido",
            "available": settings.available_timeframes,
        }

    if _process_tick is not None:
        _process_tick.active_timeframe = tf

    logger.info("Timeframe activo cambiado a: %s", tf)
    return {"active": tf, "available": settings.available_timeframes}


# ─── REST endpoints de indicadores ────────────────────────────────────

@router.get("/api/indicators/{symbol}")
async def get_indicators(
    symbol: str,
    timeframe: str | None = Query(default=None, description="Timeframe (5m, 15m, 30m, 1h)"),
) -> dict:
    """Obtener indicadores actuales de un símbolo (opcionalmente por timeframe)."""
    if _indicator_service is None:
        return {"error": "Indicator service not ready"}

    result = _indicator_service.get_indicators(symbol, timeframe)
    if result is None:
        return {"symbol": symbol, "status": "no_data"}
    return result


@router.get("/api/indicators")
async def get_all_indicators() -> dict:
    """Obtener indicadores de todos los símbolos."""
    if _indicator_service is None:
        return {"error": "Indicator service not ready"}
    return _indicator_service.get_all_indicators()


# ─── REST endpoints de señales (Fase 3) ────────────────────────────

@router.get("/api/signals/stats")
async def signal_stats() -> dict:
    """Estadísticas del motor de señales."""
    if _signal_engine is None:
        return {"error": "Signal engine not ready"}
    return _signal_engine.stats


@router.get("/api/signals/recent")
async def recent_signals(
    symbol: str | None = Query(default=None, description="Filtrar por símbolo"),
    count: int = Query(default=20, ge=1, le=50, description="Número de señales"),
) -> dict:
    """Obtener señales recientes."""
    if _signal_engine is None:
        return {"error": "Signal engine not ready", "signals": []}
    signals = _signal_engine.get_recent_signals(symbol=symbol, count=count)
    return {"count": len(signals), "signals": signals}


# ─── REST endpoints de S/R (Fase 3) ───────────────────────────────

@router.get("/api/sr/{symbol}")
async def get_sr_levels(symbol: str) -> dict:
    """Obtener niveles de soporte/resistencia de un símbolo."""
    if _sr_service is None:
        return {"error": "S/R service not ready"}
    return _sr_service.get_levels(symbol)


@router.get("/api/sr")
async def get_all_sr_levels() -> dict:
    """Obtener niveles S/R de todos los símbolos."""
    if _sr_service is None:
        return {"error": "S/R service not ready"}
    return _sr_service.get_all_levels()


# ─── REST endpoints de trades (Fase 4) ─────────────────────────────

@router.get("/api/trades/active")
async def active_trades() -> dict:
    """Trades activos (PENDING u OPEN) por símbolo."""
    if _trade_state is None:
        return {"error": "Trade state not ready", "trades": []}
    trades = _trade_state.get_all_active_trades()
    return {
        "count": len(trades),
        "trades": [t.to_dict() for t in trades],
    }


@router.get("/api/trades/history")
async def trade_history(
    symbol: str | None = Query(default=None, description="Filtrar por símbolo"),
    count: int = Query(default=50, ge=1, le=200, description="Número de trades"),
) -> dict:
    """Historial de trades cerrados (PROFIT, LOSS, EXPIRED)."""
    if _trade_state is None:
        return {"error": "Trade state not ready", "trades": []}
    trades = _trade_state.get_closed_trades(symbol=symbol)
    trades = trades[:count]
    return {
        "count": len(trades),
        "trades": [t.to_dict() for t in trades],
    }


@router.get("/api/trades/stats")
async def trade_stats() -> dict:
    """Estadísticas de paper trading."""
    if _trade_simulator is None:
        return {"error": "Trade simulator not ready"}
    return _trade_simulator.stats


# ─── REST endpoints de performance (Fase 5) ────────────────────────

@router.get("/api/stats")
async def performance_stats() -> dict:
    """
    Metricas cuantitativas globales + desglose por simbolo.

    Retorna las 12 metricas obligatorias del PRD:
      total_trades, wins, losses, expired, win_rate, loss_rate,
      profit_factor, expectancy, avg_rr_real, avg_duration,
      max_drawdown, equity_curve.

    Mas metricas complementarias: gross_profit, gross_loss,
    avg_win, avg_loss, best_trade, worst_trade, total_pnl.
    """
    if _stats_engine is None:
        return {"error": "Stats engine not ready"}
    return _stats_engine.get_all_metrics()


@router.get("/api/stats/{symbol}")
async def performance_stats_by_symbol(symbol: str) -> dict:
    """
    Metricas cuantitativas filtradas por simbolo.

    Calculo O(n) con cache lazy: solo recalcula si hay trades
    nuevos desde la ultima consulta para ese simbolo.
    """
    if _stats_engine is None:
        return {"error": "Stats engine not ready"}
    metrics = _stats_engine.get_metrics(symbol=symbol)
    return metrics.to_dict()
