"""
Market Data Bounded Context
============================
Gestiona datos de mercado: ticks, velas, indicadores técnicos, S/R.

Componentes:
- domain/: Entidades de dominio (Candle, Tick)
- services/: Servicios (CandleBuilder, IndicatorService, SRService)
- state/: Estado en memoria (MarketState, IndicatorState)
- infrastructure/: Conexión a proveedores (DerivClient, EventBus)
"""

from backend.market_data.services.candle_builder import CandleBuilder
from backend.market_data.services.indicator_service import IndicatorService
from backend.market_data.services.sr_service import SupportResistanceService
from backend.market_data.services.tf_aggregator import TimeframeAggregator
from backend.market_data.state.market_state import MarketStateManager
from backend.market_data.state.indicator_state import IndicatorStateManager

__all__ = [
    "CandleBuilder",
    "IndicatorService",
    "SupportResistanceService",
    "TimeframeAggregator",
    "MarketStateManager",
    "IndicatorStateManager",
]
