"""
Simulate Trade Use Case.

Caso de uso para simular trades basados en señales generadas.
"""

from __future__ import annotations

from typing import Optional
from decimal import Decimal
from dataclasses import dataclass

from backend.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.domain.entities.signal import Signal
from backend.domain.repositories.trade_repository import ITradeRepository
from backend.domain.services.risk_calculator import RiskCalculator
from backend.application.ports.event_publisher import IEventPublisher
from backend.domain.events.domain_events import TradeOpened, TradeClosed


@dataclass
class SimulateTradeResult:
    """Resultado de la simulación de trade."""
    trade: Optional[SimulatedTrade] = None
    opened: bool = False
    closed: bool = False
    error: Optional[str] = None


class SimulateTradeUseCase:
    """
    Caso de uso: Simular trade de paper trading.
    
    Orquesta:
    1. Apertura de trades basados en señales
    2. Actualización de estado según precio actual
    3. Cierre por SL/TP/expiración
    4. Publicación de eventos
    """
    
    def __init__(
        self,
        trade_repository: ITradeRepository,
        event_publisher: IEventPublisher,
        risk_calculator: RiskCalculator,
    ):
        self._trade_repo = trade_repository
        self._event_publisher = event_publisher
        self._risk_calculator = risk_calculator
    
    async def open_trade(self, signal: Signal) -> SimulateTradeResult:
        """
        Abre un nuevo trade simulado basado en una señal.
        
        Args:
            signal: Señal que origina el trade
        
        Returns:
            Resultado con el trade abierto
        """
        import time
        
        trade = SimulatedTrade(
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            signal_id=signal.id,
            signal_entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            rr=signal.rr,
            conditions=signal.conditions,
        )
        
        trade.entry_price = signal.entry
        trade.open_timestamp = time.time()
        trade.status = TradeStatus.PENDING
        
        await self._trade_repo.save(trade)
        
        await self._event_publisher.publish(
            TradeOpened(trade=trade, signal=signal)
        )
        
        return SimulateTradeResult(trade=trade, opened=True)
    
    async def update_trade(
        self,
        trade_id: str,
        current_price: Decimal,
    ) -> SimulateTradeResult:
        """
        Actualiza un trade con el precio actual y verifica SL/TP.
        
        Args:
            trade_id: ID del trade a actualizar
            current_price: Precio actual del mercado
        
        Returns:
            Resultado del update
        """
        trade = await self._trade_repo.find_by_id(trade_id)
        if not trade:
            return SimulateTradeResult(error=f"Trade {trade_id} not found")
        
        if trade.status != TradeStatus.PENDING:
            return SimulateTradeResult(trade=trade)
        
        price = float(current_price)
        
        # Verificar SL/TP
        if trade.signal_type == "BUY":
            if price <= trade.stop_loss:
                return await self._close_trade(trade, current_price, TradeStatus.LOSS)
            elif price >= trade.take_profit:
                return await self._close_trade(trade, current_price, TradeStatus.WIN)
        else:  # SELL
            if price >= trade.stop_loss:
                return await self._close_trade(trade, current_price, TradeStatus.LOSS)
            elif price <= trade.take_profit:
                return await self._close_trade(trade, current_price, TradeStatus.WIN)
        
        return SimulateTradeResult(trade=trade)
    
    async def _close_trade(
        self,
        trade: SimulatedTrade,
        exit_price: Decimal,
        status: TradeStatus,
    ) -> SimulateTradeResult:
        """Cierra un trade."""
        import time
        
        trade.close(float(exit_price), time.time())
        trade.status = status
        
        pnl = self._risk_calculator.calculate_pnl_percent(
            entry=trade.entry_price,
            exit_price=float(exit_price),
            signal_type=trade.signal_type,
        )
        
        await self._trade_repo.update_status(
            trade.id,
            status,
            exit_price,
            Decimal(str(pnl)),
        )
        
        await self._event_publisher.publish(
            TradeClosed(trade=trade, pnl=pnl)
        )
        
        return SimulateTradeResult(trade=trade, closed=True)
