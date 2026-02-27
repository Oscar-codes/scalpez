"""
Trading Bounded Context
========================
Gestiona la generación de señales, simulación de trades y gestión de riesgo.

Componentes:
- domain/: Entidades y servicios de dominio (Signal, Trade, Risk)
- application/: Casos de uso (GenerateSignal, SimulateTrade)
- services/: Servicios de aplicación (SignalEngine, TradeSimulator)
- state/: Estado en memoria (TradeState)
"""

from backend.trading.services.signal_engine import SignalEngine
from backend.trading.services.trade_simulator import TradeSimulator
from backend.trading.state.trade_state import TradeStateManager

__all__ = [
    "SignalEngine",
    "TradeSimulator",
    "TradeStateManager",
]
