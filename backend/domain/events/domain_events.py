"""
QuantPulse – Domain Events
============================
Eventos de dominio para arquitectura event-driven.

Los eventos de dominio representan HECHOS que ocurrieron
en el sistema. Son inmutables y llevan timestamp.

USO FUTURO:
- Event sourcing
- CQRS
- Notificaciones asíncronas
- Auditoría
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(frozen=True)
class DomainEvent:
    """Evento base de dominio."""
    
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.__class__.__name__,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class SignalGenerated(DomainEvent):
    """Evento: se generó una nueva señal de trading."""
    
    signal_id: str = ""
    symbol: str = ""
    signal_type: str = ""  # BUY | SELL
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
        })
        return base


@dataclass(frozen=True)
class TradeOpened(DomainEvent):
    """Evento: se abrió un trade."""
    
    trade_id: str = ""
    signal_id: str = ""
    symbol: str = ""
    signal_type: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "trade_id": self.trade_id,
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        })
        return base


@dataclass(frozen=True)
class TradeClosed(DomainEvent):
    """Evento: se cerró un trade."""
    
    trade_id: str = ""
    symbol: str = ""
    signal_type: str = ""
    status: str = ""  # PROFIT | LOSS | EXPIRED
    pnl_percent: float = 0.0
    duration_seconds: float = 0.0
    entry_price: float = 0.0
    close_price: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "status": self.status,
            "pnl_percent": self.pnl_percent,
            "duration_seconds": self.duration_seconds,
            "entry_price": self.entry_price,
            "close_price": self.close_price,
        })
        return base


@dataclass(frozen=True)
class SignalFiltered(DomainEvent):
    """Evento: una señal fue filtrada (por ML o reglas)."""
    
    signal_id: str = ""
    symbol: str = ""
    signal_type: str = ""
    filter_reason: str = ""  # ml_threshold, cooldown, risk, etc.
    ml_probability: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "filter_reason": self.filter_reason,
            "ml_probability": self.ml_probability,
        })
        return base
