"""
QuantPulse – Application DTO: Stats
=====================================
Data Transfer Objects para estadísticas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List

from backend.domain.value_objects.performance_metrics import PerformanceMetrics


@dataclass
class StatsResponseDTO:
    """DTO de respuesta con métricas de performance."""
    
    total_trades: int
    wins: int
    losses: int
    expired: int
    win_rate: float
    loss_rate: float
    profit_factor: float
    expectancy: float
    avg_rr_real: float
    avg_duration: float
    max_drawdown: float
    gross_profit: float
    gross_loss: float
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    total_pnl: float
    equity_curve: List[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "expired": self.expired,
            "win_rate": round(self.win_rate, 2),
            "loss_rate": round(self.loss_rate, 2),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "avg_rr_real": round(self.avg_rr_real, 4),
            "avg_duration": round(self.avg_duration, 1),
            "max_drawdown": round(self.max_drawdown, 4),
            "gross_profit": round(self.gross_profit, 4),
            "gross_loss": round(self.gross_loss, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "best_trade": round(self.best_trade, 4),
            "worst_trade": round(self.worst_trade, 4),
            "total_pnl": round(self.total_pnl, 4),
            "equity_curve": [round(e, 4) for e in (self.equity_curve or [])],
        }
    
    @classmethod
    def from_metrics(cls, metrics: PerformanceMetrics) -> "StatsResponseDTO":
        return cls(
            total_trades=metrics.total_trades,
            wins=metrics.wins,
            losses=metrics.losses,
            expired=metrics.expired,
            win_rate=metrics.win_rate,
            loss_rate=metrics.loss_rate,
            profit_factor=metrics.profit_factor,
            expectancy=metrics.expectancy,
            avg_rr_real=metrics.avg_rr_real,
            avg_duration=metrics.avg_duration,
            max_drawdown=metrics.max_drawdown,
            gross_profit=metrics.gross_profit,
            gross_loss=metrics.gross_loss,
            avg_win=metrics.avg_win,
            avg_loss=metrics.avg_loss,
            best_trade=metrics.best_trade,
            worst_trade=metrics.worst_trade,
            total_pnl=metrics.total_pnl,
            equity_curve=list(metrics.equity_curve),
        )
