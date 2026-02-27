"""
QuantPulse – Symbol ORM Model
==============================
Modelo para la tabla `symbols` (catálogo de instrumentos).

DECISIONES DE DISEÑO:

- INT UNSIGNED para ID (suficiente para catálogo pequeño).
- name es UNIQUE y el identificador de Deriv (R_100, stpRNG, etc.).
- display_name para UI amigable.
- is_active permite deshabilitar símbolos sin borrarlos.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.models.signal import SignalModel
    from backend.app.infrastructure.models.trade import TradeModel


class SymbolModel(Base):
    """Modelo ORM para símbolos/instrumentos de Deriv."""
    
    __tablename__ = "symbols"
    
    # ─── Columnas ─────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False,
        comment="Deriv symbol ID (e.g., R_100, stpRNG)"
    )
    display_name: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Nombre legible (e.g., Volatility 100)"
    )
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Si está habilitado para trading"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # ─── Relationships ────────────────────────────────────────────────
    signals: Mapped[List["SignalModel"]] = relationship(
        "SignalModel", back_populates="symbol", lazy="dynamic"
    )
    trades: Mapped[List["TradeModel"]] = relationship(
        "TradeModel", back_populates="symbol", lazy="dynamic"
    )
    
    # ─── Métodos ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serialización para API."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<Symbol(id={self.id}, name='{self.name}')>"
