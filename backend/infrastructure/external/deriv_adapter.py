"""
Deriv WebSocket Adapter.

Adapta el cliente Deriv a la interfaz IMarketDataProvider.
Proporciona acceso a datos de mercado en tiempo real desde Deriv API.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Optional, AsyncIterator, List
from decimal import Decimal

import websockets
from websockets.asyncio.client import ClientConnection

from backend.application.ports.market_data_provider import IMarketDataProvider
from backend.domain.value_objects.tick import Tick
from backend.shared.config.settings import Settings
from backend.shared.logging.logger import get_logger

logger = get_logger("deriv_adapter")

# Tópico estándar para ticks
TICK_TOPIC = "tick"


class DerivAdapter(IMarketDataProvider):
    """
    Implementación de IMarketDataProvider usando Deriv WebSocket API.
    
    Se conecta a wss://ws.derivws.com/websockets/v3 y recibe ticks
    en tiempo real de los símbolos suscritos.
    """
    
    def __init__(self, settings: Settings):
        self._settings = settings
        self._ws: Optional[ClientConnection] = None
        self._running = False
        self._subscribed_symbols: set[str] = set()
        self._tick_buffer: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10_000)
        
        # Reconexión
        self._reconnect_attempt = 0
        
        # Stats
        self._ticks_received: int = 0
        self._last_tick_time: float = 0.0
        self._connected_since: float = 0.0
    
    @property
    def ws_url(self) -> str:
        """URL del WebSocket de Deriv."""
        app_id = self._settings.deriv_app_id
        return f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
    
    # ════════════════════════════════════════════════════════════════
    #  IMarketDataProvider Implementation
    # ════════════════════════════════════════════════════════════════
    
    async def connect(self) -> None:
        """Conecta al servidor de datos de mercado."""
        if self._running:
            logger.warning("DerivAdapter ya está conectado")
            return
        
        self._running = True
        await self._connect()
        logger.info("DerivAdapter conectado")
    
    async def disconnect(self) -> None:
        """Desconecta del servidor."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        logger.info("DerivAdapter desconectado")
    
    async def subscribe(self, symbol: str) -> None:
        """Suscribe a un símbolo para recibir ticks."""
        if not self._ws:
            raise RuntimeError("No conectado. Llama a connect() primero.")
        
        subscribe_msg = {
            "ticks": symbol,
            "subscribe": 1,
        }
        await self._ws.send(json.dumps(subscribe_msg))
        self._subscribed_symbols.add(symbol)
        logger.info(f"Suscrito a símbolo: {symbol}")
    
    async def unsubscribe(self, symbol: str) -> None:
        """Cancela la suscripción a un símbolo."""
        if not self._ws or symbol not in self._subscribed_symbols:
            return
        
        unsubscribe_msg = {
            "forget_all": "ticks",
        }
        await self._ws.send(json.dumps(unsubscribe_msg))
        self._subscribed_symbols.discard(symbol)
        logger.info(f"Desuscrito de símbolo: {symbol}")
    
    async def get_ticks(self, symbol: str) -> AsyncIterator[Tick]:
        """
        Obtiene stream de ticks para un símbolo.
        
        Yields:
            Tick objects a medida que llegan
        """
        if symbol not in self._subscribed_symbols:
            await self.subscribe(symbol)
        
        while self._running:
            try:
                tick = await asyncio.wait_for(
                    self._tick_buffer.get(),
                    timeout=60.0
                )
                if tick.symbol == symbol:
                    yield tick
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error getting tick: {e}")
                break
    
    async def get_available_symbols(self) -> List[str]:
        """Obtiene lista de símbolos disponibles."""
        # Símbolos soportados por la aplicación
        return ["R_10", "R_25", "R_50", "R_75", "R_100"]
    
    # ════════════════════════════════════════════════════════════════
    #  Connection Management
    # ════════════════════════════════════════════════════════════════
    
    async def _connect(self) -> None:
        """Establece conexión WebSocket."""
        import time
        
        try:
            self._ws = await websockets.connect(self.ws_url)
            self._reconnect_attempt = 0
            self._connected_since = time.time()
            
            # Iniciar task de escucha
            asyncio.create_task(self._listen())
            asyncio.create_task(self._heartbeat())
            
        except Exception as e:
            logger.error(f"Error conectando a Deriv: {e}")
            await self._reconnect()
    
    async def _reconnect(self) -> None:
        """Reconexión con backoff exponencial."""
        if not self._running:
            return
        
        self._reconnect_attempt += 1
        base_delay = 1.0
        max_delay = 60.0
        delay = min(base_delay * (2 ** self._reconnect_attempt), max_delay)
        jitter = random.uniform(0, delay * 0.1)
        
        logger.info(f"Reconectando en {delay + jitter:.2f}s (intento {self._reconnect_attempt})")
        await asyncio.sleep(delay + jitter)
        
        await self._connect()
    
    async def _listen(self) -> None:
        """Escucha mensajes del WebSocket."""
        import time
        
        if not self._ws:
            return
        
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    
                    if "tick" in data:
                        tick_data = data["tick"]
                        tick = Tick(
                            symbol=tick_data["symbol"],
                            price=Decimal(str(tick_data["quote"])),
                            timestamp=tick_data["epoch"],
                        )
                        
                        self._ticks_received += 1
                        self._last_tick_time = time.time()
                        
                        # Agregar al buffer (drop-oldest si está lleno)
                        if self._tick_buffer.full():
                            try:
                                self._tick_buffer.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        
                        try:
                            self._tick_buffer.put_nowait(tick)
                        except asyncio.QueueFull:
                            pass
                    
                    elif "error" in data:
                        logger.error(f"Error de Deriv: {data['error']}")
                
                except json.JSONDecodeError as e:
                    logger.warning(f"Mensaje no-JSON recibido: {e}")
                except Exception as e:
                    logger.error(f"Error procesando mensaje: {e}")
        
        except websockets.ConnectionClosed:
            logger.warning("Conexión WebSocket cerrada")
            if self._running:
                await self._reconnect()
        except Exception as e:
            logger.error(f"Error en listener: {e}")
            if self._running:
                await self._reconnect()
    
    async def _heartbeat(self) -> None:
        """Envía pings periódicos para mantener la conexión."""
        while self._running and self._ws:
            try:
                await self._ws.send(json.dumps({"ping": 1}))
                await asyncio.sleep(30)
            except Exception:
                break
    
    # ════════════════════════════════════════════════════════════════
    #  Stats
    # ════════════════════════════════════════════════════════════════
    
    def get_stats(self) -> dict:
        """Obtiene estadísticas del adaptador."""
        import time
        
        return {
            "connected": self._ws is not None,
            "running": self._running,
            "ticks_received": self._ticks_received,
            "last_tick_age_sec": time.time() - self._last_tick_time if self._last_tick_time else None,
            "connected_since": self._connected_since,
            "subscribed_symbols": list(self._subscribed_symbols),
        }
