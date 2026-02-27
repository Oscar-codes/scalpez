"""
QuantPulse – WebSocket Manager (broadcast a clientes frontend)
================================================================
Gestiona conexiones WebSocket de clientes frontend y les envía
datos en tiempo real (ticks procesados + velas cerradas).

ARQUITECTURA:
  EventBus ──(tick_processed)──▸ WSManager._broadcast_loop()
  EventBus ──(candle)──────────▸ WSManager._broadcast_loop()
       │
       ▼
  [Cliente WS 1, Cliente WS 2, ...]

NO BLOQUEA EL LOOP PRINCIPAL:
- El broadcast corre como task independiente.
- Si un cliente se desconecta, se elimina limpiamente sin afectar a otros.
- El envío a cada cliente usa asyncio.wait_for con timeout para evitar
  que un cliente lento congele el broadcast.

MÚLTIPLES CLIENTES:
- Cada conexión se registra en un set.
- El broadcast es fan-out: se envía a todos simultáneamente.
"""

from __future__ import annotations

import asyncio
import json
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

from backend.app.core.logging import get_logger
from backend.app.domain.entities.candle import Candle
from backend.app.domain.entities.value_objects.tick import Tick
from backend.app.infrastructure.event_bus import EventBus

logger = get_logger("ws_manager")

TICK_PROCESSED_TOPIC = "tick_processed"
CANDLE_TOPIC = "candle"
TF_CANDLE_TOPIC = "tf_candle"
TF_INDICATORS_TOPIC = "tf_indicators"
INDICATORS_TOPIC = "indicators_updated"
SIGNAL_TOPIC = "signal"
TRADE_OPENED_TOPIC = "trade_opened"
TRADE_CLOSED_TOPIC = "trade_closed"


class WebSocketManager:
    """Gestiona conexiones frontend y broadcast de datos en tiempo real."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._clients: Set[WebSocket] = set()
        self._broadcast_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Lanzar loops de broadcast para todos los tópicos."""
        tick_queue = await self._event_bus.subscribe(
            TICK_PROCESSED_TOPIC, "ws_broadcast_tick"
        )
        candle_queue = await self._event_bus.subscribe(
            CANDLE_TOPIC, "ws_broadcast_candle"
        )
        tf_candle_queue = await self._event_bus.subscribe(
            TF_CANDLE_TOPIC, "ws_broadcast_tf_candle"
        )
        tf_indicators_queue = await self._event_bus.subscribe(
            TF_INDICATORS_TOPIC, "ws_broadcast_tf_indicators"
        )
        indicators_queue = await self._event_bus.subscribe(
            INDICATORS_TOPIC, "ws_broadcast_indicators"
        )
        signal_queue = await self._event_bus.subscribe(
            SIGNAL_TOPIC, "ws_broadcast_signal"
        )
        trade_opened_queue = await self._event_bus.subscribe(
            TRADE_OPENED_TOPIC, "ws_broadcast_trade_opened"
        )
        trade_closed_queue = await self._event_bus.subscribe(
            TRADE_CLOSED_TOPIC, "ws_broadcast_trade_closed"
        )

        self._broadcast_tasks = [
            asyncio.create_task(
                self._broadcast_loop(tick_queue, "tick"),
                name="ws-broadcast-tick",
            ),
            asyncio.create_task(
                self._broadcast_loop(candle_queue, "candle"),
                name="ws-broadcast-candle",
            ),
            asyncio.create_task(
                self._broadcast_loop(tf_candle_queue, "tf_candle"),
                name="ws-broadcast-tf-candle",
            ),
            asyncio.create_task(
                self._broadcast_loop(tf_indicators_queue, "tf_indicators"),
                name="ws-broadcast-tf-indicators",
            ),
            asyncio.create_task(
                self._broadcast_loop(indicators_queue, "indicators"),
                name="ws-broadcast-indicators",
            ),
            asyncio.create_task(
                self._broadcast_loop(signal_queue, "signal"),
                name="ws-broadcast-signal",
            ),
            asyncio.create_task(
                self._broadcast_loop(trade_opened_queue, "trade_opened"),
                name="ws-broadcast-trade-opened",
            ),
            asyncio.create_task(
                self._broadcast_loop(trade_closed_queue, "trade_closed"),
                name="ws-broadcast-trade-closed",
            ),
        ]
        logger.info(
            "WebSocketManager iniciado – broadcast loops para tick, candle, "
            "tf_candle, tf_indicators, indicators, signal, trade_opened, trade_closed"
        )

    async def stop(self) -> None:
        """Cancelar broadcast y cerrar todos los clientes."""
        for task in self._broadcast_tasks:
            task.cancel()

        # Cerrar conexiones de clientes
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        logger.info("WebSocketManager detenido")

    async def connect(self, websocket: WebSocket) -> None:
        """Registrar un nuevo cliente WebSocket."""
        await websocket.accept()
        self._clients.add(websocket)
        logger.info("Cliente WS conectado. Total: %d", len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        """Des-registrar un cliente desconectado."""
        self._clients.discard(websocket)
        logger.info("Cliente WS desconectado. Total: %d", len(self._clients))

    async def _broadcast_loop(self, queue: asyncio.Queue, event_type: str) -> None:
        """
        Loop que consume eventos de una Queue y los envía a todos los clientes.
        Corre indefinidamente en su propio task.
        """
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not self._clients:
                    continue

                # Serializar el evento
                # Usa to_dict() si el objeto lo tiene (Tick, Candle, Signal),
                # dict directo para indicadores, str como fallback.
                if hasattr(data, 'to_dict'):
                    payload_data = data.to_dict()
                elif isinstance(data, dict):
                    payload_data = data
                else:
                    payload_data = str(data)

                payload = json.dumps({
                    "type": event_type,
                    "data": payload_data,
                })

                # Broadcast a todos los clientes en paralelo
                disconnected: list[WebSocket] = []
                send_tasks = []
                for ws in self._clients:
                    send_tasks.append(self._safe_send(ws, payload, disconnected))

                if send_tasks:
                    await asyncio.gather(*send_tasks)

                # Limpiar clientes desconectados
                for ws in disconnected:
                    self._clients.discard(ws)

        except asyncio.CancelledError:
            pass  # Shutdown limpio

    async def _safe_send(
        self, ws: WebSocket, payload: str, disconnected: list[WebSocket]
    ) -> None:
        """
        Enviar payload a un cliente con timeout.
        Si falla, marcar como desconectado para limpieza.
        No lanza excepciones → no rompe el gather de broadcast.
        """
        try:
            await asyncio.wait_for(ws.send_text(payload), timeout=5.0)
        except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
            disconnected.append(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)
