"""
QuantPulse – Persistence Listener
===================================
Escucha eventos del EventBus y persiste señales/trades en MySQL.

Desacoplamiento: El SignalEngine y TradeSimulator no conocen la persistencia.
Este listener intercepta los eventos y guarda los datos de forma transparente.

ARQUITECTURA:
  EventBus (Queue-based)    PersistenceListener
       ┌──────┐                 ┌─────────────┐
       │signal│ ──────Queue────▸│ _consume()  │──▸ MySQL
       └──────┘                 │   loop      │
       ┌──────────┐             └─────────────┘
       │trade_open│ ───Queue───▸│ _consume()  │──▸ MySQL
       └──────────┘             └─────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import json
from typing import Optional, Any

from backend.shared.config.settings import settings
from backend.infrastructure.persistence.database import get_db_manager

logger = logging.getLogger("quantpulse.persistence_listener")


class PersistenceListener:
    """
    Listener que persiste señales y trades cuando se emiten eventos.
    
    Usa el EventBus queue-based: suscribe y lanza tasks que consumen de las colas.
    
    EVENTOS ESCUCHADOS:
      - 'signal': Nueva señal generada → INSERT en signals
      - 'trade_opened': Trade abierto → INSERT en trades
      - 'trade_closed': Trade cerrado → UPDATE en trades
    """
    
    def __init__(self, event_bus):
        self._event_bus = event_bus
        self._running = False
        self._tasks: list[asyncio.Task] = []
    
    async def start(self) -> None:
        """Inicia el listener de persistencia."""
        if not settings.db_enabled:
            logger.info("Persistencia deshabilitada (db_enabled=False)")
            return
        
        logger.info("Iniciando PersistenceListener...")
        self._running = True
        
        # Suscribirse a eventos y obtener colas
        signal_queue = await self._event_bus.subscribe(
            topic="signal",
            consumer_name="persistence_signal"
        )
        
        trade_opened_queue = await self._event_bus.subscribe(
            topic="trade_opened",
            consumer_name="persistence_trade_opened"
        )
        
        trade_closed_queue = await self._event_bus.subscribe(
            topic="trade_closed",
            consumer_name="persistence_trade_closed"
        )
        
        # Lanzar tasks de consumo
        self._tasks.append(asyncio.create_task(
            self._consume_loop(signal_queue, self._on_signal, "signal")
        ))
        self._tasks.append(asyncio.create_task(
            self._consume_loop(trade_opened_queue, self._on_trade_opened, "trade_opened")
        ))
        self._tasks.append(asyncio.create_task(
            self._consume_loop(trade_closed_queue, self._on_trade_closed, "trade_closed")
        ))
        
        logger.info("PersistenceListener activo – escuchando signal, trade_opened, trade_closed")
    
    async def stop(self) -> None:
        """Detiene el listener."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("PersistenceListener detenido")
    
    async def _consume_loop(self, queue: asyncio.Queue, handler, topic_name: str) -> None:
        """Loop que consume de una cola y llama al handler."""
        while self._running:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
                await handler(data)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error en consume_loop ({topic_name}): {e}")
    
    # ════════════════════════════════════════════════════════════════
    #  Event Handlers
    # ════════════════════════════════════════════════════════════════
    
    async def _on_signal(self, signal) -> None:
        """Persiste una señal cuando se genera.
        
        Args:
            signal: Signal dataclass (frozen) con campos:
                - id, symbol, signal_type, entry, stop_loss, take_profit, rr
                - timestamp, candle_timestamp, conditions, confidence
                - estimated_duration, ml_probability
        """
        try:
            from backend.app.infrastructure.models.signal import SignalModel
            from backend.app.infrastructure.models.symbol import SymbolModel
            from sqlalchemy import select
            
            db = get_db_manager()
            async with db.session() as session:
                # Obtener o crear símbolo
                symbol_name = signal.symbol
                result = await session.execute(
                    select(SymbolModel.id).where(SymbolModel.name == symbol_name)
                )
                symbol_id = result.scalar_one_or_none()
                
                if not symbol_id:
                    symbol = SymbolModel(name=symbol_name, display_name=symbol_name)
                    session.add(symbol)
                    await session.flush()
                    symbol_id = symbol.id
                
                # Crear modelo de señal
                signal_model = SignalModel(
                    uuid=signal.id,
                    symbol_id=symbol_id,
                    signal_type=signal.signal_type,
                    entry_price=signal.entry,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    rr=signal.rr,
                    conditions=list(signal.conditions),
                    confidence=signal.confidence,
                    candle_timestamp=int(signal.candle_timestamp),
                    estimated_duration=int(signal.estimated_duration) if signal.estimated_duration else 0,
                )
                
                session.add(signal_model)
                await session.commit()
                
            logger.info(f"📀 Signal persistida: {signal.id} [{symbol_name}] {signal.signal_type}")
            
        except Exception as e:
            logger.error(f"Error persistiendo signal: {e}", exc_info=True)
    
    async def _on_trade_opened(self, trade) -> None:
        """Persiste un trade cuando se abre.
        
        Args:
            trade: SimulatedTrade con status OPEN, campos:
                - id, symbol, signal_type, signal_id
                - entry_price, stop_loss, take_profit, rr
                - open_timestamp, status
        """
        try:
            from backend.app.infrastructure.models.trade import TradeModel
            from backend.app.infrastructure.models.signal import SignalModel
            from backend.app.infrastructure.models.symbol import SymbolModel
            from sqlalchemy import select
            
            db = get_db_manager()
            async with db.session() as session:
                # Obtener symbol_id
                symbol_name = trade.symbol
                result = await session.execute(
                    select(SymbolModel.id).where(SymbolModel.name == symbol_name)
                )
                symbol_id = result.scalar_one_or_none()
                
                if not symbol_id:
                    symbol = SymbolModel(name=symbol_name, display_name=symbol_name)
                    session.add(symbol)
                    await session.flush()
                    symbol_id = symbol.id
                
                # Obtener signal_id numérico (FK) desde signal UUID
                signal_uuid = trade.signal_id
                result = await session.execute(
                    select(SignalModel.id).where(SignalModel.uuid == signal_uuid)
                )
                signal_db_id = result.scalar_one_or_none()
                
                if not signal_db_id:
                    logger.warning(f"Signal no encontrada para trade: {signal_uuid}")
                    return
                
                # Crear modelo de trade
                trade_model = TradeModel(
                    uuid=trade.id,
                    symbol_id=symbol_id,
                    signal_id=signal_db_id,
                    entry_price=trade.entry_price,
                    stop_loss=trade.stop_loss,
                    take_profit=trade.take_profit,
                    status="OPEN",
                    opened_at=int(trade.open_timestamp * 1000),  # segundos → ms
                )
                
                session.add(trade_model)
                await session.commit()
                
            logger.info(f"📀 Trade abierto persistido: {trade.id} [{symbol_name}]")
            
        except Exception as e:
            logger.error(f"Error persistiendo trade_opened: {e}", exc_info=True)
    
    async def _on_trade_closed(self, trade) -> None:
        """Actualiza un trade cuando se cierra.
        
        Args:
            trade: SimulatedTrade con status PROFIT|LOSS|EXPIRED, campos:
                - id, status, close_price, pnl_percent
                - duration_seconds, close_timestamp
        """
        try:
            from backend.app.infrastructure.models.trade import TradeModel
            from sqlalchemy import select
            
            db = get_db_manager()
            async with db.session() as session:
                # Buscar trade por UUID
                trade_uuid = trade.id
                result = await session.execute(
                    select(TradeModel).where(TradeModel.uuid == trade_uuid)
                )
                trade_model = result.scalar_one_or_none()
                
                if trade_model:
                    # Actualizar campos de cierre
                    trade_model.status = trade.status.value if hasattr(trade.status, 'value') else str(trade.status)
                    trade_model.close_price = trade.close_price
                    trade_model.pnl_percent = trade.pnl_percent
                    trade_model.duration_seconds = int(trade.duration_seconds) if trade.duration_seconds else None
                    trade_model.closed_at = int(trade.close_timestamp * 1000) if trade.close_timestamp else None  # segundos → ms
                    
                    await session.commit()
                    logger.info(f"📀 Trade cerrado: {trade_uuid} → {trade_model.status} (PnL: {trade.pnl_percent:.2f}%)")
                else:
                    logger.warning(f"Trade no encontrado para cerrar: {trade_uuid}")
                    
        except Exception as e:
            logger.error(f"Error persistiendo trade_closed: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Error persistiendo trade_closed: {e}")


# Singleton
_persistence_listener: Optional[PersistenceListener] = None


def get_persistence_listener(event_bus=None) -> PersistenceListener:
    """Obtiene la instancia global del PersistenceListener."""
    global _persistence_listener
    if _persistence_listener is None and event_bus is not None:
        _persistence_listener = PersistenceListener(event_bus)
    return _persistence_listener
