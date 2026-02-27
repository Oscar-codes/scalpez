"""
QuantPulse – Trade ORM Model
==============================
Modelo para la tabla `trades` (historial de trades simulados).

DECISIONES DE DISEÑO:

- ENUM para status: PENDING, OPEN, PROFIT, LOSS, EXPIRED.
- BIGINT para timestamps (epoch ms para precisión de trading).
- close_price NULL hasta que el trade se cierra.
- pnl_percent DECIMAL(10,5) para precisión en métricas.

RELACIÓN CON ENTIDAD DE DOMINIO:
- SimulatedTrade tiene ciclo de vida mutable.
- Este modelo persiste el estado final.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String, Integer, BigInteger, ForeignKey,
    Numeric, DateTime, Enum as SQLEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database import Base
from backend.app.domain.entities.trade import TradeStatus

if TYPE_CHECKING:
    from backend.app.infrastructure.models.symbol import SymbolModel
    from backend.app.infrastructure.models.signal import SignalModel
    from backend.app.infrastructure.models.trade_features import TradeFeatureModel


class TradeModel(Base):
    """
    Modelo ORM para trades simulados (paper trading).
    
    CICLO DE VIDA:
    - Se crea en estado PENDING cuando se genera una señal.
    - Se actualiza a OPEN cuando se ejecuta al precio del primer tick.
    - Se cierra como PROFIT/LOSS/EXPIRED según resultado.
    
    CAMPOS CLAVE:
    - entry_price: Precio REAL de ejecución (puede diferir de signal.entry).
    - pnl_percent: PnL normalizado, comparable entre símbolos.
    - rr_real: RR efectivamente obtenido.
    """
    
    __tablename__ = "trades"
    
    # ─── Primary Key ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    uuid: Mapped[str] = mapped_column(
        String(12), unique=True, nullable=False,
        comment="UUID corto generado por el sistema"
    )
    
    # ─── Foreign Keys ─────────────────────────────────────────────────
    signal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("signals.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    symbol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("symbols.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    
    # ─── Prices ───────────────────────────────────────────────────────
    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False,
        comment="Precio real de entrada (del tick)"
    )
    stop_loss: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    take_profit: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    close_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), default=None,
        comment="Precio de cierre (NULL si OPEN/PENDING)"
    )
    
    # ─── Status & Result ──────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "OPEN", "PROFIT", "LOSS", "EXPIRED", name="trade_status_enum"),
        nullable=False, default="PENDING"
    )
    pnl_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None,
        comment="PnL normalizado en %"
    )
    rr_real: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), default=None,
        comment="RR real obtenido"
    )
    
    # ─── Timing ───────────────────────────────────────────────────────
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer, default=None
    )
    opened_at: Mapped[int | None] = mapped_column(
        BigInteger, default=None,
        comment="Epoch ms de apertura"
    )
    closed_at: Mapped[int | None] = mapped_column(
        BigInteger, default=None,
        comment="Epoch ms de cierre"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )
    
    # ─── Relationships ────────────────────────────────────────────────
    symbol: Mapped["SymbolModel"] = relationship(
        "SymbolModel", back_populates="trades"
    )
    signal: Mapped["SignalModel"] = relationship(
        "SignalModel", back_populates="trades"
    )
    features: Mapped[Optional["TradeFeatureModel"]] = relationship(
        "TradeFeatureModel", back_populates="trade", uselist=False
    )
    
    # ─── Table Args (índices compuestos) ──────────────────────────────
    __table_args__ = (
        Index("idx_trades_symbol_status", "symbol_id", "status"),
        Index("idx_trades_status_time", "status", "created_at"),
        Index("idx_trades_opened", "opened_at"),
    )
    
    # ─── Métodos ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serialización para API (compatible con SimulatedTrade.to_dict())."""
        return {
            "id": self.uuid,  # API expone uuid
            "signal_id": self.signal.uuid if self.signal else None,
            "symbol": self.symbol.name if self.symbol else None,
            "entry_price": float(self.entry_price),
            "stop_loss": float(self.stop_loss),
            "take_profit": float(self.take_profit),
            "close_price": float(self.close_price) if self.close_price else None,
            "status": self.status,
            "pnl_percent": float(self.pnl_percent) if self.pnl_percent else None,
            "rr_real": float(self.rr_real) if self.rr_real else None,
            "duration_seconds": self.duration_seconds,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_domain(cls, trade, signal_db_id: int, symbol_id: int) -> "TradeModel":
        """
        Crea un modelo ORM desde una entidad de dominio SimulatedTrade.
        
        Args:
            trade: domain.entities.trade.SimulatedTrade
            signal_db_id: ID (autoincrement) del signal en la BD
            symbol_id: ID del símbolo en la BD
        """
        return cls(
            uuid=trade.id,
            signal_id=signal_db_id,
            symbol_id=symbol_id,
            entry_price=Decimal(str(trade.entry_price)) if trade.entry_price else Decimal("0"),
            stop_loss=Decimal(str(trade.stop_loss)),
            take_profit=Decimal(str(trade.take_profit)),
            close_price=Decimal(str(trade.close_price)) if trade.close_price else None,
            status=trade.status.value,
            pnl_percent=Decimal(str(trade.pnl_percent)) if trade.pnl_percent else None,
            rr_real=Decimal(str(trade.rr)) if trade.rr else None,
            duration_seconds=int(trade.duration_seconds) if trade.duration_seconds else None,
            opened_at=int(trade.open_timestamp * 1000) if trade.open_timestamp else None,
            closed_at=int(trade.close_timestamp * 1000) if trade.close_timestamp else None,
        )
    
    def update_from_domain(self, trade) -> None:
        """
        Actualiza el modelo con el estado actual de la entidad de dominio.
        Usado cuando el trade cambia de estado (PENDING→OPEN, OPEN→cerrado).
        """
        self.entry_price = Decimal(str(trade.entry_price)) if trade.entry_price else self.entry_price
        self.close_price = Decimal(str(trade.close_price)) if trade.close_price else None
        self.status = trade.status.value
        self.pnl_percent = Decimal(str(trade.pnl_percent)) if trade.pnl_percent else None
        self.duration_seconds = int(trade.duration_seconds) if trade.duration_seconds else None
        self.opened_at = int(trade.open_timestamp * 1000) if trade.open_timestamp else None
        self.closed_at = int(trade.close_timestamp * 1000) if trade.close_timestamp else None
        
        # Calcular RR real si el trade cerró
        if trade.status.value in ("PROFIT", "LOSS") and trade.entry_price and trade.close_price:
            if trade.signal_type == "BUY":
                actual_move = abs(trade.close_price - trade.entry_price)
                sl_distance = abs(trade.entry_price - trade.stop_loss)
            else:
                actual_move = abs(trade.entry_price - trade.close_price)
                sl_distance = abs(trade.stop_loss - trade.entry_price)
            
            if sl_distance > 0:
                self.rr_real = Decimal(str(round(actual_move / sl_distance, 3)))
    
    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, uuid='{self.uuid}', "
            f"status={self.status}, symbol_id={self.symbol_id})>"
        )
