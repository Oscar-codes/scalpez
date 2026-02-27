"""
QuantPulse – Domain Repository Interface: Signal
==================================================
Interfaz abstracta para persistencia de señales.

Esta interfaz define el CONTRATO que debe cumplir cualquier
implementación de repositorio de señales (MySQL, PostgreSQL, 
MongoDB, InMemory para tests, etc.)

REGLA DE CLEAN ARCHITECTURE:
- Esta interfaz vive en domain/ (capa interna)
- Las implementaciones viven en infrastructure/ (capa externa)
- El domain NO conoce CÓMO se implementa, solo QUÉ métodos existen
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any

from backend.domain.entities.signal import Signal


class ISignalRepository(ABC):
    """
    Interfaz abstracta para repositorio de señales.
    
    OPERACIONES ASYNC:
    Todas las operaciones son async para no bloquear el event loop.
    Las implementaciones deben usar async/await.
    
    TRANSACCIONES:
    El repositorio no hace commit automático.
    El caller (use case) controla las transacciones.
    """

    @abstractmethod
    async def save(
        self, 
        signal: Signal, 
        symbol_id: int,
        indicators: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Persiste una señal.
        
        Args:
            signal: Entidad Signal de dominio
            symbol_id: ID del símbolo en la tabla symbols
            indicators: Dict opcional con valores de indicadores
        
        Returns:
            UUID de la señal persistida
        """
        pass

    @abstractmethod
    async def find_by_id(self, uuid: str) -> Optional[Signal]:
        """
        Busca una señal por su UUID.
        
        Args:
            uuid: Identificador único de la señal (12 chars)
        
        Returns:
            Signal si existe, None si no
        """
        pass

    @abstractmethod
    async def find_by_symbol(
        self, 
        symbol: str, 
        limit: int = 50,
        offset: int = 0,
    ) -> List[Signal]:
        """
        Busca señales por símbolo.
        
        Args:
            symbol: Nombre del símbolo (e.g. "R_100")
            limit: Máximo número de resultados
            offset: Offset para paginación
        
        Returns:
            Lista de señales ordenadas por timestamp DESC
        """
        pass

    @abstractmethod
    async def find_recent(
        self,
        hours: int = 24,
        symbol: Optional[str] = None,
    ) -> List[Signal]:
        """
        Busca señales recientes.
        
        Args:
            hours: Ventana temporal hacia atrás
            symbol: Filtrar por símbolo (opcional)
        
        Returns:
            Lista de señales en la ventana temporal
        """
        pass

    @abstractmethod
    async def count_by_symbol(self, symbol: str) -> int:
        """
        Cuenta señales por símbolo.
        
        Args:
            symbol: Nombre del símbolo
        
        Returns:
            Número total de señales
        """
        pass

    @abstractmethod
    async def get_statistics(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas agregadas de señales.
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            since: Fecha inicial (opcional)
        
        Returns:
            Dict con total, por tipo, por condición, etc.
        """
        pass
