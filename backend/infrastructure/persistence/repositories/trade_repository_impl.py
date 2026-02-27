"""
Trade Repository Implementation.

Implementación concreta del repositorio de trades usando SQLAlchemy.
Implementa la interfaz ITradeRepository del dominio.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.domain.repositories.trade_repository import ITradeRepository
from backend.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.infrastructure.persistence.models import TradeModel, SymbolModel
from backend.infrastructure.persistence.mappers.trade_mapper import TradeMapper

logger = logging.getLogger("quantpulse.infrastructure.trade_repository")


class TradeRepositoryImpl(ITradeRepository):
    """
    Implementación async del repositorio de trades.
    
    Implementa ITradeRepository usando SQLAlchemy + MySQL async.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
        self._symbol_cache: Dict[str, int] = {}
        self._mapper = TradeMapper()
    
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
    
    # ════════════════════════════════════════════════════════════════
    #  ITradeRepository Implementation
    # ════════════════════════════════════════════════════════════════
    
    async def save(self, trade: SimulatedTrade) -> str:
        """Persiste un trade y retorna su ID."""
        symbol_id = await self._get_symbol_id(trade.symbol)
        if not symbol_id:
            raise ValueError(f"Símbolo no encontrado: {trade.symbol}")
        
        # Obtener datos del modelo y crear instancia
        model_data = self._mapper.to_model(trade, 0)  # signal_db_id se resuelve después
        model = TradeModel(**model_data)
        model.symbol_id = symbol_id
        
        self._session.add(model)
        await self._session.flush()
        
        logger.debug(f"Trade guardado: id={trade.id} symbol={trade.symbol}")
        
        return trade.id
    
    async def find_by_id(self, trade_id: str) -> Optional[SimulatedTrade]:
        """Busca trade por ID."""
        result = await self._session.execute(
            select(TradeModel)
            .options(selectinload(TradeModel.symbol))
            .options(selectinload(TradeModel.signal))
            .where(TradeModel.uuid == trade_id)
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
    ) -> List[SimulatedTrade]:
        """Busca trades por símbolo."""
        symbol_id = await self._get_symbol_id(symbol)
        if not symbol_id:
            return []
        
        query = (
            select(TradeModel)
            .options(selectinload(TradeModel.symbol))
            .options(selectinload(TradeModel.signal))
            .where(TradeModel.symbol_id == symbol_id)
            .order_by(desc(TradeModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await self._session.execute(query)
        models = result.scalars().all()
        
        return [self._mapper.to_entity_from_orm(m) for m in models]
    
    async def find_open(self, symbol: Optional[str] = None) -> List[SimulatedTrade]:
        """Obtiene trades abiertos (PENDING)."""
        query = (
            select(TradeModel)
            .options(selectinload(TradeModel.symbol))
            .options(selectinload(TradeModel.signal))
            .where(TradeModel.status == TradeStatus.PENDING.value)
        )
        
        if symbol:
            symbol_id = await self._get_symbol_id(symbol)
            if symbol_id:
                query = query.where(TradeModel.symbol_id == symbol_id)
        
        query = query.order_by(TradeModel.created_at)
        
        result = await self._session.execute(query)
        models = result.scalars().all()
        
        return [self._mapper.to_entity_from_orm(m) for m in models]
    
    async def find_closed(
        self,
        limit: int = 100,
        symbol: Optional[str] = None,
    ) -> List[SimulatedTrade]:
        """Obtiene trades cerrados."""
        closed_statuses = [
            TradeStatus.WIN.value,
            TradeStatus.LOSS.value,
            TradeStatus.EXPIRED.value,
        ]
        
        query = (
            select(TradeModel)
            .options(selectinload(TradeModel.symbol))
            .options(selectinload(TradeModel.signal))
            .where(TradeModel.status.in_(closed_statuses))
        )
        
        if symbol:
            symbol_id = await self._get_symbol_id(symbol)
            if symbol_id:
                query = query.where(TradeModel.symbol_id == symbol_id)
        
        query = query.order_by(desc(TradeModel.closed_at)).limit(limit)
        
        result = await self._session.execute(query)
        models = result.scalars().all()
        
        return [self._mapper.to_entity_from_orm(m) for m in models]
    
    async def update_status(
        self,
        trade_id: str,
        status: TradeStatus,
        exit_price: Optional[Decimal] = None,
        pnl: Optional[Decimal] = None,
    ) -> bool:
        """Actualiza el estado de un trade."""
        result = await self._session.execute(
            select(TradeModel).where(TradeModel.uuid == trade_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return False
        
        model.status = status.value
        if exit_price is not None:
            model.exit_price = exit_price
        if pnl is not None:
            model.pnl = pnl
        if status != TradeStatus.PENDING:
            model.closed_at = datetime.utcnow()
        
        return True
    
    async def count_by_status(
        self,
        status: TradeStatus,
        symbol: Optional[str] = None,
    ) -> int:
        """Cuenta trades por estado."""
        query = select(func.count()).where(TradeModel.status == status.value)
        
        if symbol:
            symbol_id = await self._get_symbol_id(symbol)
            if symbol_id:
                query = query.where(TradeModel.symbol_id == symbol_id)
        
        result = await self._session.execute(query)
        return result.scalar() or 0
    
    async def calculate_stats(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        """Calcula estadísticas de trades."""
        closed_statuses = [TradeStatus.WIN.value, TradeStatus.LOSS.value]
        
        query = select(TradeModel).where(TradeModel.status.in_(closed_statuses))
        
        if symbol:
            symbol_id = await self._get_symbol_id(symbol)
            if symbol_id:
                query = query.where(TradeModel.symbol_id == symbol_id)
        
        if start_date:
            query = query.where(TradeModel.created_at >= start_date)
        if end_date:
            query = query.where(TradeModel.created_at <= end_date)
        
        result = await self._session.execute(query)
        trades = result.scalars().all()
        
        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": Decimal("0"),
                "avg_pnl": Decimal("0"),
            }
        
        wins = sum(1 for t in trades if t.status == TradeStatus.WIN.value)
        losses = len(trades) - wins
        total_pnl = sum(t.pnl or Decimal("0") for t in trades)
        
        return {
            "total_trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(trades) * 100 if trades else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(trades) if trades else Decimal("0"),
        }
    
    async def delete(self, trade_id: str) -> bool:
        """Elimina un trade por ID."""
        result = await self._session.execute(
            select(TradeModel).where(TradeModel.uuid == trade_id)
        )
        model = result.scalar_one_or_none()
        
        if model is None:
            return False
        
        await self._session.delete(model)
        return True
