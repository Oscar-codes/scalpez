"""
QuantPulse – Performance Snapshot ORM Model
=============================================
Modelo para la tabla `performance_snapshots` (métricas históricas).

PROPÓSITO:
  Captura el estado de las métricas en puntos específicos del tiempo.
  
  Útil para:
    - Tracking de evolución del sistema a lo largo del tiempo.
    - Detección de degradación de performance (drift).
    - Comparación entre períodos (semana A vs semana B).
    - Gráficos históricos de win rate, profit factor, etc.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String, Integer, ForeignKey,
    Numeric, DateTime, JSON, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.models.symbol import SymbolModel


class PerformanceSnapshotModel(Base):
    """
    Modelo ORM para snapshots de métricas de performance.
    
    RELACIÓN OPTATIVA CON SYMBOL:
    - symbol_id NULL = métricas globales (todos los símbolos).
    - symbol_id != NULL = métricas filtradas por símbolo.
    
    PERIODICIDAD:
    - Se puede crear un snapshot cada hora, día, o bajo demanda.
    - period_start/period_end definen el rango analizado.
    """
    
    __tablename__ = "performance_snapshots"
    
    # ─── Primary Key ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    
    # ─── Foreign Key (opcional) ───────────────────────────────────────
    symbol_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("symbols.id", ondelete="CASCADE"),
        default=None, index=True,
        comment="NULL = métricas globales"
    )
    
    # ─── Filtros ──────────────────────────────────────────────────────
    timeframe: Mapped[str | None] = mapped_column(
        String(8), default=None,
        comment="NULL = todos los timeframes"
    )
    
    # ─── Trade Counts ─────────────────────────────────────────────────
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expired_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # ─── Performance Metrics ──────────────────────────────────────────
    win_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), default=None,
        comment="Porcentaje 0-100"
    )
    profit_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), default=None,
        comment="Gross profit / Gross loss"
    )
    expectancy: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None,
        comment="E[PnL] por trade"
    )
    
    # ─── PnL Metrics ──────────────────────────────────────────────────
    avg_win: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None,
        comment="PnL% promedio en wins"
    )
    avg_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None,
        comment="PnL% promedio en losses (negativo)"
    )
    avg_rr_real: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), default=None
    )
    
    # ─── Risk Metrics ─────────────────────────────────────────────────
    max_drawdown: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None,
        comment="Máximo drawdown en %"
    )
    best_trade: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None
    )
    worst_trade: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5), default=None
    )
    
    # ─── Equity Tracking ──────────────────────────────────────────────
    cumulative_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 5), default=None,
        comment="PnL acumulado en %"
    )
    equity_curve: Mapped[list | None] = mapped_column(
        JSON, default=None,
        comment="Array de puntos para gráfico"
    )
    
    # ─── Period Definition ────────────────────────────────────────────
    period_start: Mapped[datetime | None] = mapped_column(
        DateTime, default=None,
        comment="Inicio del período medido"
    )
    period_end: Mapped[datetime | None] = mapped_column(
        DateTime, default=None,
        comment="Fin del período medido"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    
    # ─── Relationships ────────────────────────────────────────────────
    symbol: Mapped[Optional["SymbolModel"]] = relationship(
        "SymbolModel", lazy="joined"
    )
    
    # ─── Table Args ───────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_snapshots_symbol_time", "symbol_id", "created_at"),
        Index("idx_snapshots_time", "created_at"),
    )
    
    # ─── Métodos ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serialización para API."""
        return {
            "id": self.id,
            "symbol": self.symbol.name if self.symbol else None,
            "timeframe": self.timeframe,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "expired_trades": self.expired_trades,
            "win_rate": float(self.win_rate) if self.win_rate else None,
            "profit_factor": float(self.profit_factor) if self.profit_factor else None,
            "expectancy": float(self.expectancy) if self.expectancy else None,
            "avg_win": float(self.avg_win) if self.avg_win else None,
            "avg_loss": float(self.avg_loss) if self.avg_loss else None,
            "avg_rr_real": float(self.avg_rr_real) if self.avg_rr_real else None,
            "max_drawdown": float(self.max_drawdown) if self.max_drawdown else None,
            "best_trade": float(self.best_trade) if self.best_trade else None,
            "worst_trade": float(self.worst_trade) if self.worst_trade else None,
            "cumulative_pnl": float(self.cumulative_pnl) if self.cumulative_pnl else None,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_metrics(
        cls,
        metrics,  # PerformanceMetrics from domain
        symbol_id: int = None,
        timeframe: str = None,
        period_start: datetime = None,
        period_end: datetime = None,
    ) -> "PerformanceSnapshotModel":
        """
        Crea un snapshot desde un objeto PerformanceMetrics de dominio.
        """
        return cls(
            symbol_id=symbol_id,
            timeframe=timeframe,
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            expired_trades=metrics.expired_trades,
            win_rate=Decimal(str(metrics.win_rate)) if metrics.win_rate else None,
            profit_factor=Decimal(str(metrics.profit_factor)) if metrics.profit_factor else None,
            expectancy=Decimal(str(metrics.expectancy)) if metrics.expectancy else None,
            avg_win=Decimal(str(metrics.avg_win)) if metrics.avg_win else None,
            avg_loss=Decimal(str(metrics.avg_loss)) if metrics.avg_loss else None,
            avg_rr_real=Decimal(str(metrics.avg_rr_real)) if metrics.avg_rr_real else None,
            max_drawdown=Decimal(str(metrics.max_drawdown)) if metrics.max_drawdown else None,
            best_trade=Decimal(str(metrics.best_trade)) if metrics.best_trade else None,
            worst_trade=Decimal(str(metrics.worst_trade)) if metrics.worst_trade else None,
            cumulative_pnl=Decimal(str(metrics.cumulative_pnl)) if hasattr(metrics, 'cumulative_pnl') else None,
            equity_curve=metrics.equity_curve if hasattr(metrics, 'equity_curve') else None,
            period_start=period_start,
            period_end=period_end,
        )
    
    def __repr__(self) -> str:
        sym = self.symbol.name if self.symbol else "global"
        return (
            f"<PerformanceSnapshot(id={self.id}, symbol={sym}, "
            f"wr={self.win_rate}%, pf={self.profit_factor})>"
        )
