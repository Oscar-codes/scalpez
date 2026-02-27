"""
QuantPulse – Application DTO: Trade
=====================================
Data Transfer Objects para trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from backend.domain.entities.trade import SimulatedTrade, TradeStatus


@dataclass
class TradeResponseDTO:
    """DTO de respuesta con datos de trade."""
    
    id: str
    symbol: str
    signal_type: str
    signal_id: str
    entry_price: float
    stop_loss: float
    take_profit: float
    rr: float
    status: str
    
    # Campos de cierre (opcionales)
    close_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    duration_seconds: Optional[float] = None
    open_timestamp: float = 0.0
    close_timestamp: Optional[float] = None
    conditions: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "signal_id": self.signal_id,
            "entry_price": round(self.entry_price, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5),
            "rr": round(self.rr, 2),
            "status": self.status,
            "close_price": round(self.close_price, 5) if self.close_price else None,
            "pnl_percent": round(self.pnl_percent, 4) if self.pnl_percent else None,
            "duration_seconds": round(self.duration_seconds, 1) if self.duration_seconds else None,
            "open_timestamp": self.open_timestamp,
            "close_timestamp": self.close_timestamp,
            "conditions": self.conditions or [],
        }
    
    @classmethod
    def from_entity(cls, trade: SimulatedTrade) -> "TradeResponseDTO":
        return cls(
            id=trade.id,
            symbol=trade.symbol,
            signal_type=trade.signal_type,
            signal_id=trade.signal_id,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            rr=trade.rr,
            status=trade.status.value,
            close_price=trade.close_price if trade.is_closed else None,
            pnl_percent=trade.pnl_percent if trade.is_closed else None,
            duration_seconds=trade.duration_seconds if trade.is_closed else None,
            open_timestamp=trade.open_timestamp,
            close_timestamp=trade.close_timestamp if trade.is_closed else None,
            conditions=list(trade.conditions) if trade.conditions else [],
        )
