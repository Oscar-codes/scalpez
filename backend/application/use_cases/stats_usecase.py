"""
Stats Use Case.

Caso de uso para calcular y obtener estadísticas de trading.
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

from backend.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.domain.value_objects.performance_metrics import PerformanceMetrics
from backend.domain.repositories.trade_repository import ITradeRepository
from backend.domain.repositories.signal_repository import ISignalRepository
from backend.application.dto.stats_dto import StatsResponseDTO


@dataclass 
class StatsResult:
    """Resultado del cálculo de estadísticas."""
    stats: Optional[StatsResponseDTO] = None
    trades_analyzed: int = 0


class StatsUseCase:
    """
    Caso de uso: Calcular estadísticas de trading.
    
    Proporciona métricas de rendimiento basadas en el historial de trades.
    """
    
    def __init__(
        self,
        trade_repository: ITradeRepository,
        signal_repository: ISignalRepository,
    ):
        self._trade_repo = trade_repository
        self._signal_repo = signal_repository
    
    async def get_stats(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> StatsResult:
        """
        Calcula estadísticas para un símbolo y período.
        
        Args:
            symbol: Símbolo a filtrar (opcional)
            start_date: Fecha inicio (opcional)
            end_date: Fecha fin (opcional)
        
        Returns:
            Estadísticas calculadas
        """
        # Obtener datos de repositorios
        trade_stats = await self._trade_repo.calculate_stats(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        
        signal_count = await self._signal_repo.count_by_symbol(
            symbol=symbol or "R_100",
            start_date=start_date,
            end_date=end_date,
        ) if symbol else 0
        
        stats = StatsResponseDTO(
            total_trades=trade_stats["total_trades"],
            winning_trades=trade_stats["wins"],
            losing_trades=trade_stats["losses"],
            win_rate=trade_stats["win_rate"],
            total_pnl=float(trade_stats["total_pnl"]),
            avg_pnl=float(trade_stats["avg_pnl"]),
            total_signals=signal_count,
            symbol=symbol,
        )
        
        return StatsResult(
            stats=stats,
            trades_analyzed=trade_stats["total_trades"],
        )
    
    async def get_equity_curve(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[float]:
        """
        Obtiene la curva de equity (PnL acumulado).
        
        Args:
            symbol: Símbolo a filtrar
            limit: Número máximo de trades
        
        Returns:
            Lista de valores de PnL acumulado
        """
        trades = await self._trade_repo.find_closed(limit=limit, symbol=symbol)
        
        equity_curve = []
        cumulative = 0.0
        
        for trade in reversed(trades):  # Orden cronológico
            cumulative += trade.pnl_percent
            equity_curve.append(cumulative)
        
        return equity_curve
