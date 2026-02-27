"""
QuantPulse – Application Port: Event Publisher
================================================
Interfaz para publicar eventos a sistemas externos.

Los use cases publican eventos; la infraestructura
decide CÓMO entregar esos eventos (WebSocket, Message Bus,
etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any


class IEventPublisher(ABC):
    """
    Interfaz para publicar eventos del sistema.
    
    IMPLEMENTACIONES POSIBLES:
    - EventBusPublisher (memoria/async)
    - WebSocketPublisher (frontend)
    - RabbitMQPublisher (message queue)
    - KafkaPublisher (streaming)
    """
    
    @abstractmethod
    async def publish(
        self,
        topic: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Publica un evento a un tópico.
        
        Args:
            topic: Nombre del tópico (e.g. "signal", "trade_closed")
            data: Datos del evento (serializable a JSON)
        """
        pass
    
    @abstractmethod
    async def publish_many(
        self,
        events: list[tuple[str, Dict[str, Any]]],
    ) -> None:
        """
        Publica múltiples eventos de forma eficiente.
        
        Args:
            events: Lista de tuplas (topic, data)
        """
        pass
    
    @abstractmethod
    def subscribe(
        self,
        topic: str,
        handler: callable,
    ) -> None:
        """
        Registra un handler para un tópico.
        
        Args:
            topic: Tópico a escuchar
            handler: Función async que recibe (data: dict)
        """
        pass
