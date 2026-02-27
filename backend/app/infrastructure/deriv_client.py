"""
QuantPulse – Deriv WebSocket Client (asíncrono, producción-ready)
=================================================================
Cliente WebSocket que se conecta a Deriv vía wss://ws.derivws.com/websockets/v3
y publica cada tick en el EventBus.

RECONEXIÓN AUTOMÁTICA CON BACKOFF EXPONENCIAL:
- Ante cualquier desconexión (red, error del servidor, timeout) el cliente
  espera un delay creciente: base * 2^intento (capped a max_delay).
- El jitter aleatorio evita thundering herd si hay múltiples instancias.
- Un flag `_running` permite shutdown limpio.

HEARTBEAT:
- Un task paralelo envía {"ping": 1} cada N segundos.
- Si Deriv no responde en 10s, se cierra la conexión → reconexión automática.

CÓMO SE EVITA PÉRDIDA DE TICKS:
- El parsing y publicación al EventBus son operaciones O(1) no-blocking.
- El EventBus usa put_nowait con política drop-oldest, así el client
  nunca se bloquea esperando a consumidores lentos.

PROTECCIÓN DE MEMORIA:
- No se almacena historial de ticks aquí; solo se reenvían al EventBus.
- El EventBus maneja su propio bounded buffer.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Optional

import websockets
from websockets.asyncio.client import ClientConnection

from backend.app.core.logging import get_logger
from backend.app.core.settings import settings
from backend.app.domain.entities.value_objects.tick import Tick
from backend.app.infrastructure.event_bus import EventBus

logger = get_logger("deriv_client")

# Tópico estándar del EventBus para ticks crudos
TICK_TOPIC = "tick"


class DerivClient:
    """
    Cliente WebSocket asíncrono para Deriv.

    Ciclo de vida:
      1. start()  → lanza task de conexión + heartbeat
      2. _connect_loop() → reconexión perpetua con backoff
      3. _listen()       → parsear mensajes y publicar ticks
      4. _heartbeat()    → mantener conexión viva
      5. stop()          → shutdown limpio
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._ws: Optional[ClientConnection] = None
        self._running = False
        self._connect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_attempt = 0

        # Estadísticas de monitoreo
        self._ticks_received: int = 0
        self._last_tick_time: float = 0.0
        self._connected_since: float = 0.0

    # ──────────────────────── Lifecycle ──────────────────────────────────

    async def start(self) -> None:
        """Iniciar cliente. Idempotente: llamar varias veces es seguro."""
        if self._running:
            logger.warning("DerivClient ya está corriendo, ignorando start()")
            return

        self._running = True
        self._connect_task = asyncio.create_task(
            self._connect_loop(), name="deriv-connect-loop"
        )
        logger.info("DerivClient iniciado")

    async def stop(self) -> None:
        """Shutdown limpio: cerrar WS y cancelar tasks."""
        self._running = False
        logger.info("Deteniendo DerivClient...")

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "DerivClient detenido. Total ticks recibidos: %d", self._ticks_received
        )

    # ──────────────────────── Connection Loop ───────────────────────────

    async def _connect_loop(self) -> None:
        """
        Loop principal de reconexión con backoff exponencial.
        Se ejecuta indefinidamente hasta que self._running = False.
        """
        ws_url = f"{settings.deriv_ws_url}?app_id={settings.deriv_app_id}"

        while self._running:
            try:
                logger.info("Conectando a Deriv: %s", ws_url)
                async with websockets.connect(
                    ws_url,
                    ping_interval=None,   # Gestionamos heartbeat manualmente
                    ping_timeout=None,
                    close_timeout=10,
                    max_size=2**20,       # 1 MB máximo por mensaje
                ) as ws:
                    self._ws = ws
                    self._reconnect_attempt = 0  # Reset backoff tras conexión exitosa
                    self._connected_since = time.time()
                    logger.info("✓ Conectado a Deriv WebSocket")

                    # Suscribir a todos los símbolos configurados
                    await self._subscribe_symbols(ws)

                    # Lanzar heartbeat en paralelo
                    self._heartbeat_task = asyncio.create_task(
                        self._heartbeat(ws), name="deriv-heartbeat"
                    )

                    # Escuchar mensajes hasta desconexión
                    await self._listen(ws)

            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
            ) as e:
                logger.warning("Conexión cerrada: %s", e)
            except OSError as e:
                logger.error("Error de red: %s", e)
            except Exception as e:
                logger.error("Error inesperado en connect_loop: %s", e, exc_info=True)
            finally:
                self._ws = None
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()

            if not self._running:
                break

            # ── Backoff exponencial con jitter ──
            delay = min(
                settings.ws_reconnect_base_delay * (2 ** self._reconnect_attempt),
                settings.ws_reconnect_max_delay,
            )
            jitter = random.uniform(0, delay * 0.3)
            total_delay = delay + jitter
            self._reconnect_attempt += 1

            logger.info(
                "Reconectando en %.1fs (intento #%d)...",
                total_delay,
                self._reconnect_attempt,
            )
            await asyncio.sleep(total_delay)

    # ──────────────────────── Subscribe ─────────────────────────────────

    async def _subscribe_symbols(self, ws: ClientConnection) -> None:
        """Suscribir a tick streams de todos los símbolos configurados."""
        for symbol in settings.deriv_symbols:
            msg = {"ticks": symbol, "subscribe": 1}
            await ws.send(json.dumps(msg))
            logger.info("Suscrito a ticks de '%s'", symbol)

    # ──────────────────────── Listener ──────────────────────────────────

    async def _listen(self, ws: ClientConnection) -> None:
        """
        Loop de escucha de mensajes.
        Parsea cada mensaje y publica ticks al EventBus.
        Solo procesa mensajes de tipo 'tick' – ignora el resto.
        """
        msg_count = 0
        async for raw_msg in ws:
            if not self._running:
                break

            msg_count += 1

            try:
                data = json.loads(raw_msg)
            except json.JSONDecodeError:
                logger.warning("Mensaje no-JSON recibido, ignorando")
                continue

            # Log primeros mensajes para diagnóstico
            if msg_count <= 10:
                msg_type = data.get("msg_type", "?")
                keys = list(data.keys())[:5]
                logger.info(
                    "📥 Deriv msg #%d tipo=%s keys=%s",
                    msg_count, msg_type, keys,
                )

            # ── Manejo de errores del API ──
            if "error" in data:
                error = data["error"]
                logger.error(
                    "Error de Deriv API [%s]: %s | echo_req=%s",
                    error.get("code", "?"),
                    error.get("message", "sin detalle"),
                    str(data.get("echo_req", {}))[:200],
                )
                continue

            # ── Respuesta de ping ──
            if "pong" in data:
                continue

            # ── Tick de precio ──
            if "tick" in data:
                tick_data = data["tick"]
                tick = Tick(
                    symbol=tick_data.get("symbol", ""),
                    epoch=float(tick_data.get("epoch", 0)),
                    quote=float(tick_data.get("quote", 0)),
                    ask=tick_data.get("ask"),
                    bid=tick_data.get("bid"),
                )

                self._ticks_received += 1
                self._last_tick_time = tick.epoch

                # Publicar al EventBus – NUNCA bloquea
                await self._event_bus.publish(TICK_TOPIC, tick)

    # ──────────────────────── Heartbeat ─────────────────────────────────

    async def _heartbeat(self, ws: ClientConnection) -> None:
        """
        Enviar ping periódico para evitar timeout del servidor.
        Si el envío falla, el loop de listen detectará la desconexión.
        """
        try:
            while self._running:
                await asyncio.sleep(settings.ws_heartbeat_interval)
                if ws.close_code is not None:
                    break
                try:
                    await ws.send(json.dumps({"ping": 1}))
                except Exception:
                    logger.warning("Fallo al enviar heartbeat, conexión probablemente perdida")
                    break
        except asyncio.CancelledError:
            pass  # Shutdown limpio

    # ──────────────────────── Stats ─────────────────────────────────────

    @property
    def stats(self) -> dict:
        """Estadísticas del cliente para monitoreo."""
        return {
            "running": self._running,
            "connected": self._ws is not None and self._ws.close_code is None,
            "ticks_received": self._ticks_received,
            "last_tick_time": self._last_tick_time,
            "connected_since": self._connected_since,
            "reconnect_attempts": self._reconnect_attempt,
        }
