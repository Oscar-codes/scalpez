"""
QuantPulse – Application Port: Market Data Provider
=====================================================
Interfaz para obtener datos de mercado.

Los use cases solicitan datos; la infraestructura
decide CÓMO obtenerlos (WebSocket Deriv, API REST,
base de datos histórica, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator

from backend.domain.value_objects.tick import Tick
from backend.domain.entities.candle import Candle


class IMarketDataProvider(ABC):
    """
    Interfaz para proveer datos de mercado.
    
    IMPLEMENTACIONES POSIBLES:
    - DerivWebSocketProvider (real-time)
    - HistoricalDataProvider (backtesting)
    - MockDataProvider (testing)
    """
    
    @abstractmethod
    async def connect(self, symbol: str) -> bool:
        """
        Establece conexión para recibir datos de un símbolo.
        
        Args:
            symbol: Símbolo a suscribir (e.g. "R_100")
        
        Returns:
            True si conexión exitosa
        """
        pass
    
    @abstractmethod
    async def disconnect(self, symbol: str) -> None:
        """
        Cierra conexión de un símbolo.
        
        Args:
            symbol: Símbolo a desuscribir
        """
        pass
    
    @abstractmethod
    async def get_tick_stream(
        self,
        symbol: str,
    ) -> AsyncIterator[Tick]:
        """
        Obtiene stream de ticks en tiempo real.
        
        Args:
            symbol: Símbolo a escuchar
        
        Yields:
            Tick objects a medida que llegan
        """
        pass
    
    @abstractmethod
    async def get_historical_candles(
        self,
        symbol: str,
        interval: int,
        limit: int = 100,
    ) -> List[Candle]:
        """
        Obtiene velas históricas.
        
        Args:
            symbol: Símbolo
            interval: Intervalo en segundos
            limit: Número máximo de velas
        
        Returns:
            Lista de velas ordenadas por timestamp ASC
        """
        pass
    
    @abstractmethod
    async def get_last_price(self, symbol: str) -> Optional[float]:
        """
        Obtiene el último precio conocido.
        
        Args:
            symbol: Símbolo
        
        Returns:
            Último precio, o None si no disponible
        """
        pass
    
    @abstractmethod
    def is_connected(self, symbol: str) -> bool:
        """
        Verifica si hay conexión activa para un símbolo.
        
        Args:
            symbol: Símbolo a verificar
        
        Returns:
            True si conectado
        """
        pass
