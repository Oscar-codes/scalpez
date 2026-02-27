"""
QuantPulse – Domain Layer
===========================
Núcleo puro del sistema. CERO dependencias externas.

Este módulo contiene:
- entities/: Entidades de negocio (Signal, Trade, Candle)
- value_objects/: Objetos inmutables (Tick, PerformanceMetrics)
- services/: Servicios de dominio puros (SignalRules, RiskCalculator)
- repositories/: Interfaces abstractas (ABCs)
- events/: Eventos de dominio
- exceptions/: Excepciones de dominio

REGLA DE DEPENDENCIA:
Este módulo NO puede importar de:
- infrastructure/
- presentation/
- application/
- Frameworks externos (SQLAlchemy, FastAPI, etc.)
"""

from backend.domain.entities.signal import Signal
from backend.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.domain.entities.candle import Candle
from backend.domain.value_objects.tick import Tick
from backend.domain.value_objects.performance_metrics import PerformanceMetrics

__all__ = [
    "Signal",
    "SimulatedTrade",
    "TradeStatus",
    "Candle",
    "Tick",
    "PerformanceMetrics",
]
