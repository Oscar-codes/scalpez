"""
Signal Repository Implementation.

Implementación concreta del repositorio de señales usando SQLAlchemy.
Implementa la interfaz ISignalRepository del dominio.

Clean Architecture: Esta clase está en infrastructure y depende de domain.
El dominio NO conoce esta implementación.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.domain.repositories.signal_repository import ISignalRepository
from backend.domain.entities.signal import Signal
from backend.infrastructure.persistence.models import SignalModel, SymbolModel
from backend.infrastructure.persistence.mappers.signal_mapper import SignalMapper

logger = logging.getLogger("quantpulse.infrastructure.signal_repository")


class SignalRepositoryImpl(ISignalRepository):
    """
    Implementación async del repositorio de señales.
    
    Implementa ISignalRepository usando SQLAlchemy + MySQL async.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
        self._symbol_cache: Dict[str, int] = {}
        self._mapper = SignalMapper()
    
    # ════════════════════════════════════════════════════════════════
    #  SYMBOL RESOLUTION
    # ════════════════════════════════════════════════════════════════
    
    async def _get_symbol_id(self, symbol_name: str) -> Optional[int]:
        """Obtiene el ID del símbolo con cache."""
        if symbol_name in self._symbol_cache:
            return self._symbol_cache[symbol_name]
        
        result = await self._session.execute(
            select(SymbolModel.id).where(SymbolModel.name == symbol_name)
        )
        row = result.scalar_one_or_none()
        
        if row:
            self._symbol_cache[symbol_name] = row
        
        return row
    
    async def _get_or_create_symbol(self, name: str) -> int:
        """Obtiene o crea un símbolo."""
        symbol_id = await self._get_symbol_id(name)
        if symbol_id:
            return symbol_id
        
        symbol = SymbolModel(name=name, display_name=name)
        self._session.add(symbol)
        await self._session.flush()
        
        self._symbol_cache[name] = symbol.id
        return symbol.id
    
    # ════════════════════════════════════════════════════════════════
    #  ISignalRepository Implementation
    # ════════════════════════════════════════════════════════════════
    
    async def save(self, signal: Signal) -> str:
        """Persiste una señal y retorna su UUID."""
        symbol_id = await self._get_or_create_symbol(signal.symbol)
        
        # Usar mapper para obtener datos del modelo
        model_data = self._mapper.to_model(signal, symbol_id)
        
        # Crear instancia del modelo ORM
        model = SignalModel(**model_data)
        
        self._session.add(model)
        await self._session.flush()
        
        logger.debug(f"Signal guardada: uuid={signal.id} symbol={signal.symbol}")
        
        return signal.id
    
    async def find_by_id(self, signal_id: str) -> Optional[Signal]:
        """Busca señal por UUID."""
        result = await self._session.execute(
            select(SignalModel)
            .options(selectinload(SignalModel.symbol))
            .where(SignalModel.uuid == signal_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return None
        
        return self._mapper.to_entity_from_orm(model)
    
    async def find_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Signal]:
        """Busca señales por símbolo."""
        symbol_id = await self._get_symbol_id(symbol)
        if not symbol_id:
            return []
        
        query = (
            select(SignalModel)
            .options(selectinload(SignalModel.symbol))
            .where(SignalModel.symbol_id == symbol_id)
            .order_by(desc(SignalModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await self._session.execute(query)
        models = result.scalars().all()
        
        return [self._mapper.to_entity_from_orm(m) for m in models]
    
    async def find_recent(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
    ) -> List[Signal]:
        """Obtiene las señales más recientes."""
        query = select(SignalModel).options(selectinload(SignalModel.symbol))
        
        if symbol:
            symbol_id = await self._get_symbol_id(symbol)
            if symbol_id:
                query = query.where(SignalModel.symbol_id == symbol_id)
        
        query = query.order_by(desc(SignalModel.created_at)).limit(limit)
        
        result = await self._session.execute(query)
        models = result.scalars().all()
        
        return [self._mapper.to_entity_from_orm(m) for m in models]
    
    async def count_by_symbol(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Cuenta señales por símbolo en un rango de fechas."""
        symbol_id = await self._get_symbol_id(symbol)
        if not symbol_id:
            return 0
        
        query = select(func.count()).where(SignalModel.symbol_id == symbol_id)
        
        if start_date:
            query = query.where(SignalModel.created_at >= start_date)
        if end_date:
            query = query.where(SignalModel.created_at <= end_date)
        
        result = await self._session.execute(query)
        return result.scalar() or 0
    
    async def delete(self, signal_id: str) -> bool:
        """Elimina una señal por UUID."""
        result = await self._session.execute(
            select(SignalModel).where(SignalModel.uuid == signal_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return False
        
        await self._session.delete(model)
        return True
