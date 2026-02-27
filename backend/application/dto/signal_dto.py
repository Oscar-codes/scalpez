"""
QuantPulse – Application DTO: Signal
======================================
Data Transfer Objects para señales.

Los DTOs sirven como contratos entre capas.
Son estructuras simples sin lógica de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from backend.domain.entities.signal import Signal


@dataclass
class SignalRequestDTO:
    """DTO para solicitar generación de señal."""
    
    symbol: str
    close: float
    high: float
    low: float
    candle_timestamp: float
    
    # Indicadores pre-calculados
    ema_fast: float
    ema_slow: float
    prev_ema_fast: float
    prev_ema_slow: float
    rsi: float
    prev_rsi: float
    
    # Niveles S/R
    support: float
    resistance: float
    swing_low: float
    swing_high: float
    
    # Volatilidad
    avg_range: float
    recent_ranges: List[float] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalRequestDTO":
        return cls(
            symbol=data["symbol"],
            close=data["close"],
            high=data["high"],
            low=data["low"],
            candle_timestamp=data["candle_timestamp"],
            ema_fast=data.get("ema_fast", 0),
            ema_slow=data.get("ema_slow", 0),
            prev_ema_fast=data.get("prev_ema_fast", 0),
            prev_ema_slow=data.get("prev_ema_slow", 0),
            rsi=data.get("rsi", 50),
            prev_rsi=data.get("prev_rsi", 50),
            support=data.get("support", 0),
            resistance=data.get("resistance", 0),
            swing_low=data.get("swing_low", 0),
            swing_high=data.get("swing_high", 0),
            avg_range=data.get("avg_range", 0),
            recent_ranges=data.get("recent_ranges"),
        )


@dataclass
class SignalResponseDTO:
    """DTO de respuesta con señal generada."""
    
    id: str
    symbol: str
    signal_type: str
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    timestamp: float
    candle_timestamp: float
    conditions: List[str]
    confidence: int
    estimated_duration: float
    
    # Campos opcionales de ML
    ml_probability: Optional[float] = None
    ml_filtered: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "entry": round(self.entry, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5),
            "rr": round(self.rr, 2),
            "timestamp": self.timestamp,
            "candle_timestamp": self.candle_timestamp,
            "conditions": self.conditions,
            "confidence": self.confidence,
            "estimated_duration": round(self.estimated_duration, 1),
            "ml_probability": round(self.ml_probability, 4) if self.ml_probability else None,
            "ml_filtered": self.ml_filtered,
        }
    
    @classmethod
    def from_entity(cls, signal: Signal, ml_probability: float = None, ml_filtered: bool = False) -> "SignalResponseDTO":
        return cls(
            id=signal.id,
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            rr=signal.rr,
            timestamp=signal.timestamp,
            candle_timestamp=signal.candle_timestamp,
            conditions=list(signal.conditions),
            confidence=signal.confidence,
            estimated_duration=signal.estimated_duration,
            ml_probability=ml_probability,
            ml_filtered=ml_filtered,
        )
