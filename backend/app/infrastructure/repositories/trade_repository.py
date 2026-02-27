"""
QuantPulse – Trade Repository (Async MySQL)
=============================================
Repositorio para persistencia de trades simulados.

PATRÓN REPOSITORY:
  - Abstrae el acceso a datos de la lógica de dominio.
  - Maneja el ciclo de vida completo del trade (PENDING → cerrado).
  - Incluye persistencia de features ML.

OPERACIONES ASYNC:
  - Todas las operaciones son async para no bloquear el event loop.
  - Batch updates para cerrar múltiples trades eficientemente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select, func, and_, or_, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.app.infrastructure.models.trade import TradeModel
from backend.app.infrastructure.models.trade_features import TradeFeatureModel
from backend.app.infrastructure.models.symbol import SymbolModel

logger = logging.getLogger("quantpulse.trade_repository")


class TradeRepository:
    """
    Repositorio async para operaciones CRUD de trades.
    
    USO:
        repo = TradeRepository(session)
        trade_id = await repo.save(trade, signal_db_id, symbol_id)
        await repo.update_status(trade)
        trades = await repo.find_closed(limit=100)
    
    NOTAS DE RENDIMIENTO:
    - Usa índices compuestos para queries de status + tiempo.
    - Update parcial para cambios de estado (no reescribe todo el row).
    - Batch operations para procesamiento de múltiples trades.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
        self._symbol_cache: Dict[str, int] = {}  # name → id cache
    
    # ════════════════════════════════════════════════════════════════
    #  SYMBOL RESOLUTION
    # ════════════════════════════════════════════════════════════════
    
    async def get_symbol_id(self, symbol_name: str) -> Optional[int]:
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
    #  CREATE
    # ════════════════════════════════════════════════════════════════
    
    async def save(
        self,
        trade: SimulatedTrade,
        signal_db_id: int,
        symbol_name: str = None,
    ) -> int:
        """
        Persiste un trade en la BD.
        
        Args:
            trade: Entidad SimulatedTrade del dominio
            signal_db_id: ID de la señal en la BD (autoincrement)
            symbol_name: Nombre del símbolo (usa trade.symbol si None)
        
        Returns:
            ID del trade persistido
        """
        symbol_name = symbol_name or trade.symbol
        symbol_id = await self.get_symbol_id(symbol_name)
        
        if not symbol_id:
            raise ValueError(f"Símbolo no encontrado: {symbol_name}")
        
        model = TradeModel.from_domain(trade, signal_db_id, symbol_id)
        
        self._session.add(model)
        await self._session.flush()
        
        logger.debug(
            f"Trade guardado: uuid={model.uuid} symbol={symbol_name} "
            f"status={trade.status.value} db_id={model.id}"
        )
        
        return model.id
    
    async def save_with_features(
        self,
        trade: SimulatedTrade,
        signal_db_id: int,
        indicators: dict,
        candle,
        sr_context: dict = None,
    ) -> Tuple[int, int]:
        """
        Guarda trade + features ML en una transacción.
        
        Returns:
            (trade_id, features_id)
        """
        # Guardar trade
        trade_id = await self.save(trade, signal_db_id)
        
        # Crear y guardar features
        features = TradeFeatureModel.from_context(
            trade_id=trade_id,
            indicators=indicators,
            candle=candle,
            conditions=list(trade.conditions) if trade.conditions else [],
            sr_context=sr_context,
            timestamp=datetime.utcnow(),
        )
        
        self._session.add(features)
        await self._session.flush()
        
        logger.debug(f"Features guardadas para trade {trade_id}: pattern={features.pattern_type}")
        
        return trade_id, features.id
    
    # ════════════════════════════════════════════════════════════════
    #  UPDATE
    # ════════════════════════════════════════════════════════════════
    
    async def update_status(self, trade: SimulatedTrade) -> bool:
        """
        Actualiza el estado de un trade existente.
        Busca por uuid y actualiza campos de estado/resultado.
        
        Returns:
            True si se actualizó, False si no se encontró.
        """
        result = await self._session.execute(
            select(TradeModel).where(TradeModel.uuid == trade.id)
        )
        model = result.scalar_one_or_none()
        
        if not model:
            logger.warning(f"Trade no encontrado para update: {trade.id}")
            return False
        
        model.update_from_domain(trade)
        await self._session.flush()
        
        logger.debug(
            f"Trade actualizado: uuid={trade.id} status={trade.status.value} "
            f"pnl={trade.pnl_percent:.4f}%"
        )
        
        return True
    
    async def bulk_update_status(
        self,
        updates: List[Tuple[str, str, float, int]],  # (uuid, status, pnl, closed_at)
    ) -> int:
        """
        Actualización masiva de estados.
        Más eficiente que N updates individuales.
        
        Returns:
            Número de trades actualizados.
        """
        count = 0
        for uuid, status, pnl, closed_at in updates:
            result = await self._session.execute(
                update(TradeModel)
                .where(TradeModel.uuid == uuid)
                .values(
                    status=status,
                    pnl_percent=Decimal(str(pnl)) if pnl else None,
                    closed_at=closed_at,
                    updated_at=datetime.utcnow(),
                )
            )
            count += result.rowcount
        
        return count
    
    # ════════════════════════════════════════════════════════════════
    #  READ
    # ════════════════════════════════════════════════════════════════
    
    async def find_by_id(self, trade_id: int) -> Optional[TradeModel]:
        """Busca trade por ID (autoincrement)."""
        result = await self._session.execute(
            select(TradeModel)
            .options(
                selectinload(TradeModel.symbol),
                selectinload(TradeModel.signal),
                selectinload(TradeModel.features),
            )
            .where(TradeModel.id == trade_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_uuid(self, uuid: str) -> Optional[TradeModel]:
        """Busca trade por UUID (el ID público)."""
        result = await self._session.execute(
            select(TradeModel)
            .options(
                selectinload(TradeModel.symbol),
                selectinload(TradeModel.signal),
                selectinload(TradeModel.features),
            )
            .where(TradeModel.uuid == uuid)
        )
        return result.scalar_one_or_none()
    
    async def find_active(self, symbol_name: str = None) -> List[TradeModel]:
        """
        Busca trades activos (PENDING u OPEN).
        
        ÍNDICE USADO: idx_trades_symbol_status
        """
        query = (
            select(TradeModel)
            .options(selectinload(TradeModel.symbol))
            .where(TradeModel.status.in_(["PENDING", "OPEN"]))
        )
        
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                query = query.where(TradeModel.symbol_id == symbol_id)
        
        result = await self._session.execute(query)
        return list(result.scalars().all())
    
    async def find_closed(
        self,
        limit: int = 100,
        offset: int = 0,
        symbol_name: str = None,
        status: str = None,  # "PROFIT", "LOSS", "EXPIRED"
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> List[TradeModel]:
        """
        Busca trades cerrados con filtros y paginación.
        
        ÍNDICE USADO: idx_trades_status_time
        """
        closed_statuses = ["PROFIT", "LOSS", "EXPIRED"]
        
        query = (
            select(TradeModel)
            .options(
                selectinload(TradeModel.symbol),
                selectinload(TradeModel.features),
            )
        )
        
        filters = []
        
        if status:
            filters.append(TradeModel.status == status)
        else:
            filters.append(TradeModel.status.in_(closed_statuses))
        
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(TradeModel.symbol_id == symbol_id)
        
        if start_date:
            filters.append(TradeModel.closed_at >= int(start_date.timestamp() * 1000))
        if end_date:
            filters.append(TradeModel.closed_at <= int(end_date.timestamp() * 1000))
        
        query = (
            query.where(and_(*filters))
            .order_by(desc(TradeModel.closed_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await self._session.execute(query)
        return list(result.scalars().all())
    
    async def find_recent(
        self,
        limit: int = 50,
        include_active: bool = True,
    ) -> List[TradeModel]:
        """
        Busca trades más recientes (activos + cerrados).
        Ordenados por created_at DESC.
        """
        query = (
            select(TradeModel)
            .options(
                selectinload(TradeModel.symbol),
                selectinload(TradeModel.features),
            )
            .order_by(desc(TradeModel.created_at))
            .limit(limit)
        )
        
        if not include_active:
            query = query.where(TradeModel.status.in_(["PROFIT", "LOSS", "EXPIRED"]))
        
        result = await self._session.execute(query)
        return list(result.scalars().all())
    
    # ════════════════════════════════════════════════════════════════
    #  ML DATASET
    # ════════════════════════════════════════════════════════════════
    
    async def get_ml_dataset(
        self,
        symbol_name: str = None,
        limit: int = 10000,
        only_resolved: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene dataset para entrenamiento ML.
        
        Retorna trades con features + label (PROFIT=1, LOSS=0).
        
        USO EN ML:
            dataset = await repo.get_ml_dataset(limit=5000)
            X = pd.DataFrame([d['features'] for d in dataset])
            y = pd.Series([d['label'] for d in dataset])
        """
        query = (
            select(TradeModel, TradeFeatureModel)
            .join(TradeFeatureModel, TradeModel.id == TradeFeatureModel.trade_id)
            .options(selectinload(TradeModel.symbol))
        )
        
        filters = []
        if only_resolved:
            filters.append(TradeModel.status.in_(["PROFIT", "LOSS"]))
        
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(TradeModel.symbol_id == symbol_id)
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.order_by(TradeModel.opened_at).limit(limit)
        
        result = await self._session.execute(query)
        rows = result.all()
        
        dataset = []
        for trade, features in rows:
            dataset.append({
                "trade_id": trade.uuid,
                "symbol": trade.symbol.name if trade.symbol else None,
                "label": 1 if trade.status == "PROFIT" else 0,
                "pnl_percent": float(trade.pnl_percent) if trade.pnl_percent else 0,
                "rr_real": float(trade.rr_real) if trade.rr_real else 0,
                "features": features.to_ml_features(),
                "opened_at": trade.opened_at,
            })
        
        return dataset
    
    # ════════════════════════════════════════════════════════════════
    #  ANALYTICS
    # ════════════════════════════════════════════════════════════════
    
    async def count_by_status(
        self,
        symbol_name: str = None,
        start_date: datetime = None,
    ) -> Dict[str, int]:
        """
        Cuenta trades por estado.
        
        Returns:
            {"PROFIT": 45, "LOSS": 30, "EXPIRED": 5, "OPEN": 2, "PENDING": 0}
        """
        filters = []
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(TradeModel.symbol_id == symbol_id)
        if start_date:
            filters.append(TradeModel.created_at >= start_date)
        
        query = (
            select(TradeModel.status, func.count(TradeModel.id))
            .group_by(TradeModel.status)
        )
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await self._session.execute(query)
        return {row[0]: row[1] for row in result.all()}
    
    async def get_performance_summary(
        self,
        symbol_name: str = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Obtiene resumen de performance para un período.
        
        IMPORTANTE: No reemplaza StatsEngine - esto es para queries históricas
        desde la BD, mientras StatsEngine trabaja con trades en memoria.
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        filters = [
            TradeModel.status.in_(["PROFIT", "LOSS"]),
            TradeModel.created_at >= start_date,
        ]
        
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(TradeModel.symbol_id == symbol_id)
        
        # Agregaciones
        query = select(
            func.count(TradeModel.id).label("total"),
            func.sum(
                func.cast(TradeModel.status == "PROFIT", Decimal)
            ).label("wins"),
            func.avg(TradeModel.pnl_percent).label("avg_pnl"),
            func.sum(TradeModel.pnl_percent).label("total_pnl"),
            func.max(TradeModel.pnl_percent).label("best"),
            func.min(TradeModel.pnl_percent).label("worst"),
            func.avg(TradeModel.duration_seconds).label("avg_duration"),
        ).where(and_(*filters))
        
        result = await self._session.execute(query)
        row = result.one()
        
        total = row[0] or 0
        wins = int(row[1] or 0)
        
        return {
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": total - wins,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "avg_pnl": float(row[2]) if row[2] else 0,
            "cumulative_pnl": float(row[3]) if row[3] else 0,
            "best_trade": float(row[4]) if row[4] else 0,
            "worst_trade": float(row[5]) if row[5] else 0,
            "avg_duration_seconds": float(row[6]) if row[6] else 0,
            "days": days,
        }
    
    async def get_equity_curve(
        self,
        symbol_name: str = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene puntos para graficar equity curve desde la BD.
        
        Returns:
            [{"timestamp": 123456, "cumulative_pnl": 2.5, "trade_id": "abc123"}, ...]
        """
        filters = [TradeModel.status.in_(["PROFIT", "LOSS"])]
        
        if symbol_name:
            symbol_id = await self.get_symbol_id(symbol_name)
            if symbol_id:
                filters.append(TradeModel.symbol_id == symbol_id)
        
        query = (
            select(TradeModel.uuid, TradeModel.closed_at, TradeModel.pnl_percent)
            .where(and_(*filters))
            .order_by(TradeModel.closed_at)
            .limit(limit)
        )
        
        result = await self._session.execute(query)
        rows = result.all()
        
        curve = []
        cumulative = 0.0
        
        for uuid, closed_at, pnl in rows:
            cumulative += float(pnl) if pnl else 0
            curve.append({
                "trade_id": uuid,
                "timestamp": closed_at,
                "pnl": float(pnl) if pnl else 0,
                "cumulative_pnl": round(cumulative, 4),
            })
        
        return curve
