"""
Event Bus Adapter.

Adapta el EventBus existente a la interfaz IEventPublisher del dominio.
Permite publicar Domain Events sin acoplar el dominio a la infraestructura.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional, List, Callable, Awaitable

from backend.application.ports.event_publisher import IEventPublisher
from backend.domain.events.domain_events import DomainEvent
from backend.shared.logging.logger import get_logger

logger = get_logger("event_bus_adapter")


class EventBusAdapter(IEventPublisher):
    """
    Implementación de IEventPublisher usando asyncio.Queue fan-out.
    
    Convierte Domain Events a mensajes publicables y los distribuye
    a todos los consumidores suscritos.
    """
    
    def __init__(self, max_queue_size: int = 10_000):
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, List[tuple[asyncio.Queue, str]]] = {}
        self._handlers: dict[str, List[Callable[[DomainEvent], Awaitable[None]]]] = {}
        self._lock = asyncio.Lock()
    
    async def publish(self, event: DomainEvent) -> None:
        """
        Publica un Domain Event.
        
        El evento se convierte a dict y se distribuye a todos los
        consumidores suscritos al tipo de evento.
        """
        event_type = event.__class__.__name__
        event_data = event.to_dict()
        
        logger.debug(f"Publishing event: {event_type}")
        
        # Publicar a handlers registrados
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Error in handler for {event_type}: {e}")
        
        # Publicar a colas de suscriptores
        subscribers = self._subscribers.get(event_type, [])
        for queue, consumer_name in subscribers:
            if queue.full():
                # Drop-oldest policy
                try:
                    queue.get_nowait()
                    logger.warning(
                        f"Queue full for '{consumer_name}' on event '{event_type}' - old event dropped"
                    )
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                logger.error(f"Could not enqueue event for '{consumer_name}'")
    
    async def publish_all(self, events: List[DomainEvent]) -> None:
        """Publica múltiples eventos en secuencia."""
        for event in events:
            await self.publish(event)
    
    def register_handler(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        """
        Registra un handler para un tipo de evento.
        
        El handler será llamado cada vez que se publique un evento
        del tipo especificado.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.info(f"Handler registered for event type: {event_type}")
    
    async def subscribe(self, event_type: str, consumer_name: str) -> asyncio.Queue:
        """
        Suscribe un consumidor a un tipo de evento.
        
        Retorna una Queue exclusiva para ese consumidor.
        """
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append((queue, consumer_name))
            logger.info(f"Consumer '{consumer_name}' subscribed to '{event_type}'")
            return queue
    
    async def unsubscribe_all(self, event_type: Optional[str] = None) -> None:
        """Desuscribe todos los consumidores de un tipo de evento o todos."""
        async with self._lock:
            if event_type:
                self._subscribers.pop(event_type, None)
                self._handlers.pop(event_type, None)
            else:
                self._subscribers.clear()
                self._handlers.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Legacy EventBus wrapper (para compatibilidad con código existente)
# ═══════════════════════════════════════════════════════════════════════════

class LegacyEventBus:
    """
    Wrapper del EventBus original para compatibilidad.
    
    Permite publicar datos raw (no Domain Events) como el EventBus original.
    """
    
    def __init__(self, max_queue_size: int = 10_000):
        self._max_queue_size = max_queue_size
        self._subscribers: dict[str, List[tuple[asyncio.Queue, str]]] = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, topic: str, consumer_name: str) -> asyncio.Queue:
        """Registrar un consumidor en un tópico."""
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append((queue, consumer_name))
            logger.info(f"Consumer '{consumer_name}' subscribed to topic '{topic}'")
            return queue
    
    async def publish(self, topic: str, data: any) -> None:
        """Publicar evento raw a un tópico."""
        subscribers = self._subscribers.get(topic, [])
        for queue, consumer_name in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                pass
    
    async def unsubscribe_all(self, topic: Optional[str] = None) -> None:
        """Desuscribir todos los consumidores."""
        async with self._lock:
            if topic:
                self._subscribers.pop(topic, None)
            else:
                self._subscribers.clear()


# Global instance for legacy compatibility
_legacy_event_bus: Optional[LegacyEventBus] = None


def get_legacy_event_bus() -> LegacyEventBus:
    """Obtiene la instancia global del EventBus legacy."""
    global _legacy_event_bus
    if _legacy_event_bus is None:
        _legacy_event_bus = LegacyEventBus()
    return _legacy_event_bus
