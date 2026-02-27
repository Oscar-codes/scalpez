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
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.logging import get_logger

logger = get_logger("api.routes")

router = APIRouter()

# Referencias a componentes inyectados desde main.py
_ws_manager = None
_market_state = None
_deriv_client = None
_indicator_service = None


def init_routes(ws_manager, market_state, deriv_client, indicator_service=None) -> None:
    """Inyectar dependencias desde main.py al arrancar."""
    global _ws_manager, _market_state, _deriv_client, _indicator_service
    _ws_manager = ws_manager
    _market_state = market_state
    _deriv_client = deriv_client
    _indicator_service = indicator_service


# ─── WebSocket endpoint para streaming a frontend ─────────────────────

@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint principal.
    El frontend se conecta aquí para recibir ticks, velas e indicadores
    en tiempo real. El broadcast lo maneja WebSocketManager – este handler
    solo gestiona el ciclo de vida de la conexión.
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
    """Estado completo del sistema incluyendo indicadores."""
    result = {
        "market_state": _market_state.snapshot() if _market_state else {},
        "deriv_client": _deriv_client.stats if _deriv_client else {},
        "ws_clients": _ws_manager.client_count if _ws_manager else 0,
        "indicators": _indicator_service.get_all_indicators() if _indicator_service else {},
    }
    return result


@router.get("/api/candles/{symbol}")
async def get_candles(symbol: str, count: int = 50) -> dict:
    """Obtener últimas N velas de un símbolo."""
    if _market_state is None:
        return {"error": "Server not ready", "candles": []}

    count = min(count, 200)
    candles = _market_state.get_candles(symbol, count)
    return {
        "symbol": symbol,
        "count": len(candles),
        "candles": [c.to_dict() for c in candles],
    }


# ─── REST endpoints de indicadores ────────────────────────────────────

@router.get("/api/indicators/{symbol}")
async def get_indicators(symbol: str) -> dict:
    """Obtener indicadores actuales de un símbolo."""
    if _indicator_service is None:
        return {"error": "Indicator service not ready"}

    result = _indicator_service.get_indicators(symbol)
    if result is None:
        return {"symbol": symbol, "status": "no_data"}
    return result


@router.get("/api/indicators")
async def get_all_indicators() -> dict:
    """Obtener indicadores de todos los símbolos."""
    if _indicator_service is None:
        return {"error": "Indicator service not ready"}
    return _indicator_service.get_all_indicators()
