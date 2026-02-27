"""
QuantPulse – Trade Mapper
===========================
Mapea entre SimulatedTrade (domain entity) y TradeModel (ORM).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from backend.domain.entities.trade import SimulatedTrade, TradeStatus


class TradeMapper:
    """
    Mapper bidireccional SimulatedTrade ↔ TradeModel.
    """
    
    def to_model(
        self,
        trade: SimulatedTrade,
        signal_db_id: int,
    ) -> Dict[str, Any]:
        """
        Convierte SimulatedTrade entity a dict para crear TradeModel.
        
        Args:
            trade: Entidad de dominio
            signal_db_id: ID de la señal origen en BD
        
        Returns:
            Dict con campos para TradeModel
        """
        return {
            "uuid": trade.id,
            "signal_id": signal_db_id,
            "status": trade.status.value,
            "entry_price": Decimal(str(round(trade.entry_price, 8))) if trade.entry_price else None,
            "close_price": Decimal(str(round(trade.close_price, 8))) if trade.close_price else None,
            "pnl_percent": Decimal(str(round(trade.pnl_percent, 6))) if trade.is_closed else None,
            "opened_at": datetime.fromtimestamp(trade.open_timestamp) if trade.open_timestamp else None,
            "closed_at": datetime.fromtimestamp(trade.close_timestamp) if trade.close_timestamp else None,
            "duration_seconds": int(trade.duration_seconds) if trade.duration_seconds else None,
        }
    
    def to_entity_from_orm(self, model: Any, symbol: str = "") -> SimulatedTrade:
        """
        Convierte TradeModel ORM directamente a SimulatedTrade entity.
        
        Args:
            model: Instancia de TradeModel ORM
            symbol: Nombre del símbolo
        
        Returns:
            SimulatedTrade entity
        """
        # Obtener datos de la señal relacionada
        signal = model.signal
        
        trade = SimulatedTrade(
            symbol=symbol or (signal.symbol.name if hasattr(signal, 'symbol') else ""),
            signal_type=signal.signal_type if signal else "",
            signal_id=signal.uuid if signal else "",
            signal_entry=float(signal.entry_price) if signal else 0.0,
            stop_loss=float(signal.stop_loss) if signal else 0.0,
            take_profit=float(signal.take_profit) if signal else 0.0,
            rr=float(signal.rr_ratio) if signal else 0.0,
            conditions=tuple(signal.conditions or []) if signal else (),
        )
        
        # Sobrescribir campos generados
        trade.id = model.uuid
        trade.status = TradeStatus(model.status)
        trade.entry_price = float(model.entry_price) if model.entry_price else 0.0
        trade.close_price = float(model.close_price) if model.close_price else 0.0
        trade.pnl_percent = float(model.pnl_percent) if model.pnl_percent else 0.0
        trade.open_timestamp = model.opened_at.timestamp() if model.opened_at else 0.0
        trade.close_timestamp = model.closed_at.timestamp() if model.closed_at else 0.0
        trade.duration_seconds = float(model.duration_seconds) if model.duration_seconds else 0.0
        
        return trade
