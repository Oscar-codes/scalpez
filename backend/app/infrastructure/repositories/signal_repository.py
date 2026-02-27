"""
QuantPulse – Signal Repository (Async MySQL)
==============================================
Repositorio para persistencia de señales de trading.

PATRÓN REPOSITORY:
  - Abstrae el acceso a datos de la lógica de dominio.
  - Facilita testing con mocks.
  - Centraliza queries complejas.

OPERACIONES ASYNC:
  - Todas las operaciones son async para no bloquear el event loop.
  - Crítico para alta frecuencia de trading.

TRANSACCIONES:
  - El caller controla commit/rollback.
  - El repositorio no hace commit automático.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.domain.entities.signal import Signal
from backend.app.infrastructure.models.signal import SignalModel
from backend.app.infrastructure.models.symbol import SymbolModel

logger = logging.getLogger("quantpulse.signal_repository")


class SignalRepository:
    """
    Repositorio async para operaciones CRUD de señales.
    
    USO:
        repo = SignalRepository(session)
        signal_id = await repo.save(signal, symbol_id, indicators)
        signals = await repo.find_by_symbol("R_100", limit=50)
    
    NOTAS DE RENDIMIENTO:
    - Usa índices compuestos (symbol_id, created_at) para queries rápidas.
    - Evita SELECT * cuando solo se necesitan IDs o conteos.
    - Batch inserts para alta frecuencia (save_batch).
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
        self._symbol_cache: Dict[str, int] = {}  # name → id cache
    
    # ════════════════════════════════════════════════════════════════
    #  SYMBOL RESOLUTION (con cache)
    # ════════════════════════════════════════════════════════════════
    
    async def get_symbol_id(self, symbol_name: str) -> Optional[int]:
        """
        Obtiene el ID del símbolo, usando cache en memoria.
        
        POR QUÉ CACHE:
        - Los símbolos son ~4 registros que nunca cambian en runtime.
        - Evita un SELECT por cada save().
        """
        if symbol_name in self._symbol_cache:
            return self._symbol_cache[symbol_name]
        
        result = await self._session.execute(
            select(SymbolModel.id).where(SymbolModel.name == symbol_name)
        )
        row = result.scalar_one_or_none()
        
        if row:
            self._symbol_cache[symbol_name] = row
        
        return row
    
    async def get_or_create_symbol(
        self, 
        name: str, 
        display_name: str = None
    ) -> int:
        """
        Obtiene o crea un símbolo. Retorna el ID.
        """
        symbol_id = await self.get_symbol_id(name)
        if symbol_id:
            return symbol_id
        
        # Crear nuevo símbolo
        symbol = SymbolModel(
            name=name,
            display_name=display_name or name,
        )
        self._session.add(symbol)
        await self._session.flush()  # Obtener ID sin commit
        
        self._symbol_cache[name] = symbol.id
        logger.info(f"Símbolo creado: {name} (id={symbol.id})")
        
        return symbol.id
    
    # ════════════════════════════════════════════════════════════════
    #  CREATE
    # ════════════════════════════════════════════════════════════════
    
    async def save(
        self,
        signal: Signal,
        indicators: dict = None,
        timeframe: str = "5s",
    ) -> int:
        """
        Persiste una señal de dominio en la BD.
        
        Args:
            signal: Entidad Signal del dominio
            indicators: Dict con ema_9, ema_21, rsi_14, support, resistance
            timeframe: Timeframe de la vela
        
        Returns:
            ID (autoincrement) de la señal persistida
        
        NOTA: No hace commit. El caller debe llamar session.commit().
        """
        # Resolver symbol_id
        symbol_id = await self.get_or_create_symbol(signal.symbol)
        
        # Enriquecer indicators con timeframe
        indicators = indicators or {}
        indicators["timeframe"] = timeframe
        
        # Crear modelo ORM
        model = SignalModel.from_domain(signal, symbol_id, indicators)
        
        self._session.add(model)
        await self._session.flush()  # Obtener ID
        
        logger.debug(
            f"Signal guardada: uuid={model.uuid} symbol={signal.symbol} "
            f"type={signal.signal_type} db_id={model.id}"
        )
        
        return model.id
    
    async def save_batch(
        self,
        signals: List[tuple],  # List of (Signal, indicators_dict, timeframe)
    ) -> List[int]:
        """
        Guarda múltiples señales en batch (más eficiente).
        
        Returns:
            Lista de IDs generados.
        """
        models = []
        for signal, indicators, timeframe in signals:
            symbol_id = await self.get_or_create_symbol(signal.symbol)
            indicators = indicators or {}
            indicators["timeframe"] = timeframe
            model = SignalModel.from_domain(signal, symbol_id, indicators)
            models.append(model)
        
        self._session.add_all(models)
        await self._session.flush()
        
        return [m.id for m in models]
    
    # ════════════════════════════════════════════════════════════════
    #  READ
    # ════════════════════════════════════════════════════════════════
    
    async def find_by_id(self, signal_id: int) -> Optional[SignalModel]:
        """Busca señal por ID (autoincrement)."""
        result = await self._session.execute(
            select(SignalModel)
            .options(selectinload(SignalModel.symbol))
            .where(SignalModel.id == signal_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_uuid(self, uuid: str) -> Optional[SignalModel]:
        """Busca señal por UUID (el ID público)."""
        result = await self._session.execute(
            select(SignalModel)
            .options(selectinload(SignalModel.symbol))
            .where(SignalModel.uuid == uuid)
        )
        return result.scalar_one_or_none()
    
    async def find_by_symbol(
        self,
        symbol_name: str,
        limit: int = 100,
        offset: int = 0,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> List[SignalModel]:
        """
        Busca señales por símbolo con paginación.
        
        ÍNDICE USADO: idx_signals_symbol_time (symbol_id, created_at)
        """
        symbol_id = await self.get_symbol_id(symbol_name)
        if not symbol_id:
            return []
        
        query = (
            select(SignalModel)
            .options(selectinload(SignalModel.symbol))
            .where(SignalModel.symbol_id == symbol_id)
        )
        
        if start_date:
            query = query.where(SignalModel.created_at >= start_date)
        if end_date:
            query = query.where(SignalModel.created_at <= end_date)
        
        query = query.order_by(desc(SignalModel.created_at)).limit(limit).offset(offset)
        
        result = await self._session.execute(query)
        return list(result.scalars().all())
    
    async def find_recent(
        self,
        limit: int = 50,
        symbol_name: str = None,
        signal_type: str = None,
        timeframe: str = None,
    ) -> List[SignalModel]:
        """
        Busca señales recientes con filtros opcionales.
        Ordenadas por created_at DESC.
        """
        query = select(SignalModel).options(selectinload(SignalModel.symbol))
        
        filters = []
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(SignalModel.symbol_id == symbol_id)
        if signal_type:
            filters.append(SignalModel.signal_type == signal_type)
        if timeframe:
            filters.append(SignalModel.timeframe == timeframe)
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(desc(SignalModel.created_at)).limit(limit)
        
        result = await self._session.execute(query)
        return list(result.scalars().all())
    
    # ════════════════════════════════════════════════════════════════
    #  ANALYTICS
    # ════════════════════════════════════════════════════════════════
    
    async def count_by_symbol(
        self,
        symbol_name: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> int:
        """Cuenta señales con filtros opcionales."""
        query = select(func.count(SignalModel.id))
        
        filters = []
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(SignalModel.symbol_id == symbol_id)
        if start_date:
            filters.append(SignalModel.created_at >= start_date)
        if end_date:
            filters.append(SignalModel.created_at <= end_date)
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await self._session.execute(query)
        return result.scalar() or 0
    
    async def get_signal_distribution(
        self,
        days: int = 7,
        symbol_name: str = None,
    ) -> Dict[str, Any]:
        """
        Obtiene distribución de señales por tipo en los últimos N días.
        
        Returns:
            {
                "BUY": 45,
                "SELL": 38,
                "total": 83,
                "by_pattern": {"ema_cross": 30, "sr_bounce": 25, ...}
            }
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Filtro base
        filters = [SignalModel.created_at >= start_date]
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(SignalModel.symbol_id == symbol_id)
        
        # Count by type
        type_query = (
            select(SignalModel.signal_type, func.count(SignalModel.id))
            .where(and_(*filters))
            .group_by(SignalModel.signal_type)
        )
        type_result = await self._session.execute(type_query)
        type_counts = {row[0]: row[1] for row in type_result.all()}
        
        # Count by pattern
        pattern_query = (
            select(SignalModel.pattern_detected, func.count(SignalModel.id))
            .where(and_(*filters))
            .group_by(SignalModel.pattern_detected)
        )
        pattern_result = await self._session.execute(pattern_query)
        pattern_counts = {row[0] or "unknown": row[1] for row in pattern_result.all()}
        
        return {
            "BUY": type_counts.get("BUY", 0),
            "SELL": type_counts.get("SELL", 0),
            "total": sum(type_counts.values()),
            "by_pattern": pattern_counts,
            "days": days,
        }
    
    async def get_avg_indicators(
        self,
        symbol_name: str,
        signal_type: str = None,
        days: int = 30,
    ) -> Dict[str, float]:
        """
        Obtiene promedios de indicadores para análisis.
        Útil para detectar drift o calibrar umbrales.
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        symbol_id = await self.get_symbol_id(symbol_name)
        
        if not symbol_id:
            return {}
        
        filters = [
            SignalModel.symbol_id == symbol_id,
            SignalModel.created_at >= start_date,
        ]
        if signal_type:
            filters.append(SignalModel.signal_type == signal_type)
        
        query = select(
            func.avg(SignalModel.ema9),
            func.avg(SignalModel.ema21),
            func.avg(SignalModel.rsi),
            func.avg(SignalModel.rr),
            func.count(SignalModel.id),
        ).where(and_(*filters))
        
        result = await self._session.execute(query)
        row = result.one()
        
        return {
            "avg_ema9": float(row[0]) if row[0] else None,
            "avg_ema21": float(row[1]) if row[1] else None,
            "avg_rsi": float(row[2]) if row[2] else None,
            "avg_rr": float(row[3]) if row[3] else None,
            "count": row[4],
        }
