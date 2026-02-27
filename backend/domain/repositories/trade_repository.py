"""
QuantPulse – Domain Repository Interface: Trade
=================================================
Interfaz abstracta para persistencia de trades simulados.

Define el contrato para cualquier implementación de
repositorio de trades (MySQL, PostgreSQL, InMemory, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any

from backend.domain.entities.trade import SimulatedTrade, TradeStatus


class ITradeRepository(ABC):
    """
    Interfaz abstracta para repositorio de trades.
    
    OPERACIONES ASYNC:
    Todas las operaciones son async para no bloquear el event loop.
    
    TRANSACCIONES:
    El repositorio no hace commit automático.
    El caller (use case) controla las transacciones.
    """

    @abstractmethod
    async def save(
        self, 
        trade: SimulatedTrade,
        signal_db_id: int,
    ) -> int:
        """
        Persiste un trade.
        
        Args:
            trade: Entidad SimulatedTrade de dominio
            signal_db_id: ID de la señal origen en BD
        
        Returns:
            ID del trade en BD
        """
        pass

    @abstractmethod
    async def update(self, trade: SimulatedTrade) -> bool:
        """
        Actualiza un trade existente.
        
        Args:
            trade: Trade con datos actualizados
        
        Returns:
            True si se actualizó, False si no existe
        """
        pass

    @abstractmethod
    async def find_by_id(self, trade_id: str) -> Optional[SimulatedTrade]:
        """
        Busca un trade por su UUID.
        
        Args:
            trade_id: Identificador único del trade (12 chars)
        
        Returns:
            SimulatedTrade si existe, None si no
        """
        pass

    @abstractmethod
    async def find_by_symbol(
        self, 
        symbol: str, 
        status: Optional[TradeStatus] = None,
        limit: int = 50,
    ) -> List[SimulatedTrade]:
        """
        Busca trades por símbolo.
        
        Args:
            symbol: Nombre del símbolo
            status: Filtrar por estado (opcional)
            limit: Máximo número de resultados
        
        Returns:
            Lista de trades ordenados por timestamp DESC
        """
        pass

    @abstractmethod
    async def find_closed(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SimulatedTrade]:
        """
        Busca trades cerrados para cálculo de métricas.
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            since: Desde fecha (opcional)
            limit: Máximo resultados
        
        Returns:
            Lista de trades cerrados (PROFIT, LOSS, EXPIRED)
        """
        pass

    @abstractmethod
    async def get_performance_data(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene datos para cálculo de PerformanceMetrics.
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            since: Desde fecha (opcional)
        
        Returns:
            Dict con datos agregados para StatsEngine
        """
        pass

    @abstractmethod
    async def save_features(
        self,
        trade_db_id: int,
        features: Dict[str, Any],
    ) -> int:
        """
        Persiste features de ML asociadas a un trade.
        
        Args:
            trade_db_id: ID del trade en BD
            features: Dict con features numéricas y categóricas
        
        Returns:
            ID del registro de features
        """
        pass
