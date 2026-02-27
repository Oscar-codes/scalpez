"""
QuantPulse – Event Bus (asyncio.Queue fan-out)
===============================================
Bus de eventos interno para desacoplar productores (DerivClient) de
consumidores (ProcessTickUseCase, WebSocket broadcaster, futuros motores).

Arquitectura:
  ┌──────────┐         ┌───────────┐
  │  Deriv   │──tick──▸│ Event Bus │──▸ Consumer 1 (ProcessTick)
  │  Client  │         │ (fan-out) │──▸ Consumer 2 (WS broadcast)
  └──────────┘         └───────────┘──▸ Consumer N ...

CÓMO SE EVITA PÉRDIDA DE TICKS:
- Cada consumidor tiene su propia asyncio.Queue con tamaño limitado.
- Si un consumidor es lento y su cola se llena, se descarta el tick MÁS
  ANTIGUO de esa cola (política drop-oldest), protegiendo al productor
  de bloqueos y evitando back-pressure hacia Deriv.
- Los consumidores rápidos NUNCA pierden ticks.

CÓMO SE PROTEGE MEMORIA:
- Cada cola tiene un maxsize configurable (default 10,000).
- drop-oldest previene crecimiento ilimitado.

THREAD-SAFETY:
- asyncio.Queue es safe dentro del mismo event loop, que es nuestro caso.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Callable, Awaitable

from backend.app.core.logging import get_logger

logger = get_logger("event_bus")


class EventBus:
    """Fan-out event bus basado en asyncio.Queue."""

    def __init__(self, max_queue_size: int = 10_000) -> None:
        self._max_queue_size = max_queue_size
        # topic → lista de (queue, nombre_consumidor)
        self._subscribers: Dict[str, list[tuple[asyncio.Queue, str]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, consumer_name: str) -> asyncio.Queue:
        """
        Registrar un consumidor en un tópico.
        Retorna la Queue exclusiva de ese consumidor.
        """
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append((queue, consumer_name))
            logger.info(
                "Consumidor '%s' suscrito a tópico '%s' (max_queue=%d)",
                consumer_name,
                topic,
                self._max_queue_size,
            )
            return queue

    async def publish(self, topic: str, data: Any) -> None:
        """
        Publicar un evento a todos los suscriptores de un tópico.
        Política drop-oldest si la cola está llena → el productor NUNCA se bloquea.
        """
        subscribers = self._subscribers.get(topic, [])
        for queue, consumer_name in subscribers:
            if queue.full():
                # Drop-oldest: sacar el tick más viejo para hacer espacio
                try:
                    queue.get_nowait()
                    logger.warning(
                        "Cola llena para '%s' en tópico '%s' – tick antiguo descartado",
                        consumer_name,
                        topic,
                    )
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                # Esto no debería ocurrir tras el drop-oldest, pero por seguridad
                logger.error(
                    "No se pudo encolar evento para '%s' (tópico '%s')",
                    consumer_name,
                    topic,
                )

    async def unsubscribe_all(self, topic: str | None = None) -> None:
        """Desuscribir todos los consumidores (cleanup al shutdown)."""
        async with self._lock:
            if topic:
                self._subscribers.pop(topic, None)
                logger.info("Todos los suscriptores del tópico '%s' eliminados", topic)
            else:
                self._subscribers.clear()
                logger.info("Todos los suscriptores eliminados (shutdown)")

    @property
    def subscriber_count(self) -> int:
        return sum(len(subs) for subs in self._subscribers.values())
