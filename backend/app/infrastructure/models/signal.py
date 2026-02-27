"""
QuantPulse – Signal ORM Model
==============================
Modelo para la tabla `signals` (historial de señales de trading).

DECISIONES DE DISEÑO:

- uuid CHAR(12): ID corto generado por el sistema (compatible con Signal entity).
- DECIMAL(20,8) para precios: precisión de hasta 20 dígitos totales, 8 decimales.
- JSON para conditions: array flexible de condiciones activadas.
- Indices compuestos para queries comunes (symbol + time, type + time).

RELACIÓN CON ENTIDAD DE DOMINIO:
- Este modelo mapea a/desde domain.entities.Signal.
- La conversión se hace en el repositorio (no aquí).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    String, Integer, BigInteger, ForeignKey, 
    Numeric, DateTime, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.models.symbol import SymbolModel
    from backend.app.infrastructure.models.trade import TradeModel


class SignalModel(Base):
    """
    Modelo ORM para señales de trading.
    
    CAMPOS CLAVE PARA ML:
    - ema9, ema21, rsi: Features numéricas directas para modelos.
    - pattern_detected: Feature categórica (one-hot encoding).
    - conditions: Array auditable de qué activó la señal.
    """
    
    __tablename__ = "signals"
    
    # ─── Primary Key ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    uuid: Mapped[str] = mapped_column(
        String(12), unique=True, nullable=False,
        comment="UUID corto generado por el sistema"
    )
    
    # ─── Foreign Key ──────────────────────────────────────────────────
    symbol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("symbols.id", ondelete="RESTRICT"), 
        nullable=False, index=True
    )
    
    # ─── Signal Type ──────────────────────────────────────────────────
    signal_type: Mapped[str] = mapped_column(
        SQLEnum("BUY", "SELL", name="signal_type_enum"),
        nullable=False
    )
    
    # ─── Risk Management Prices ───────────────────────────────────────
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False,
        comment="Precio de entrada sugerido"
    )
    stop_loss: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    take_profit: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    rr: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False,
        comment="Risk-Reward ratio calculado"
    )
    
    # ─── Technical Indicators ─────────────────────────────────────────
    ema9: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), default=None)
    ema21: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), default=None)
    rsi: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), default=None,
        comment="RSI 14 (0-100)"
    )
    
    # ─── Structural Context ───────────────────────────────────────────
    pattern_detected: Mapped[str | None] = mapped_column(
        String(64), default=None,
        comment="Patrón: ema_cross, sr_bounce, breakout, etc."
    )
    conditions: Mapped[list] = mapped_column(
        JSON, nullable=False,
        comment="Array de condiciones que activaron la señal"
    )
    confidence: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Número de condiciones confirmadas (2-5)"
    )
    support_level: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), default=None
    )
    resistance_level: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), default=None
    )
    
    # ─── Timeframe & Timing ───────────────────────────────────────────
    timeframe: Mapped[str] = mapped_column(
        String(8), nullable=False, default="5s",
        comment="Timeframe de la vela (5s, 1m, 5m)"
    )
    estimated_duration: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="Duración estimada en segundos"
    )
    candle_timestamp: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Epoch ms de la vela confirmante"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    
    # ─── Relationships ────────────────────────────────────────────────
    symbol: Mapped["SymbolModel"] = relationship(
        "SymbolModel", back_populates="signals"
    )
    trades: Mapped[List["TradeModel"]] = relationship(
        "TradeModel", back_populates="signal", lazy="dynamic"
    )
    
    # ─── Table Args (índices compuestos) ──────────────────────────────
    __table_args__ = (
        Index("idx_signals_symbol_time", "symbol_id", "created_at"),
        Index("idx_signals_type_time", "signal_type", "created_at"),
        Index("idx_signals_timeframe", "timeframe", "created_at"),
    )
    
    # ─── Métodos ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serialización para API (compatible con Signal.to_dict())."""
        return {
            "id": self.uuid,  # API expone uuid, no el autoincrement
            "symbol": self.symbol.name if self.symbol else None,
            "signal_type": self.signal_type,
            "entry": float(self.entry_price),
            "stop_loss": float(self.stop_loss),
            "take_profit": float(self.take_profit),
            "rr": float(self.rr),
            "ema9": float(self.ema9) if self.ema9 else None,
            "ema21": float(self.ema21) if self.ema21 else None,
            "rsi": float(self.rsi) if self.rsi else None,
            "pattern_detected": self.pattern_detected,
            "conditions": self.conditions,
            "confidence": self.confidence,
            "support_level": float(self.support_level) if self.support_level else None,
            "resistance_level": float(self.resistance_level) if self.resistance_level else None,
            "timeframe": self.timeframe,
            "estimated_duration": self.estimated_duration,
            "candle_timestamp": self.candle_timestamp,
            "timestamp": self.created_at.timestamp() if self.created_at else None,
        }
    
    @classmethod
    def from_domain(cls, signal, symbol_id: int, indicators: dict = None) -> "SignalModel":
        """
        Crea un modelo ORM desde una entidad de dominio Signal.
        
        Args:
            signal: domain.entities.Signal
            symbol_id: ID del símbolo en la BD
            indicators: dict con ema9, ema21, rsi, support, resistance
        """
        indicators = indicators or {}
        
        # Detectar patrón principal de las condiciones
        pattern = None
        if signal.conditions:
            pattern = signal.conditions[0]  # Primera condición como patrón principal
        
        return cls(
            uuid=signal.id,
            symbol_id=symbol_id,
            signal_type=signal.signal_type,
            entry_price=Decimal(str(signal.entry)),
            stop_loss=Decimal(str(signal.stop_loss)),
            take_profit=Decimal(str(signal.take_profit)),
            rr=Decimal(str(signal.rr)),
            ema9=Decimal(str(indicators.get("ema_9"))) if indicators.get("ema_9") else None,
            ema21=Decimal(str(indicators.get("ema_21"))) if indicators.get("ema_21") else None,
            rsi=Decimal(str(indicators.get("rsi_14"))) if indicators.get("rsi_14") else None,
            pattern_detected=pattern,
            conditions=list(signal.conditions),
            confidence=signal.confidence,
            support_level=Decimal(str(indicators.get("support"))) if indicators.get("support") else None,
            resistance_level=Decimal(str(indicators.get("resistance"))) if indicators.get("resistance") else None,
            timeframe=indicators.get("timeframe", "5s"),
            estimated_duration=int(signal.estimated_duration),
            candle_timestamp=int(signal.candle_timestamp * 1000),  # epoch s → ms
        )
    
    def __repr__(self) -> str:
        return (
            f"<Signal(id={self.id}, uuid='{self.uuid}', "
            f"type={self.signal_type}, symbol_id={self.symbol_id})>"
        )
