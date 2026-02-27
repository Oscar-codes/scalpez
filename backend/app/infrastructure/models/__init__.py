"""
QuantPulse – ORM Models Package
================================
Modelos SQLAlchemy para persistencia en MySQL.

ESTRUCTURA:
    models/
    ├── __init__.py       # Exports
    ├── symbol.py         # Catálogo de símbolos
    ├── signal.py         # Señales de trading
    ├── trade.py          # Trades simulados
    ├── trade_features.py # Features ML
    └── performance.py    # Snapshots de métricas

USO:
    from backend.app.infrastructure.models import (
        SymbolModel, SignalModel, TradeModel, TradeFeatureModel
    )
"""

from backend.app.infrastructure.models.symbol import SymbolModel
from backend.app.infrastructure.models.signal import SignalModel
from backend.app.infrastructure.models.trade import TradeModel
from backend.app.infrastructure.models.trade_features import TradeFeatureModel
from backend.app.infrastructure.models.performance import PerformanceSnapshotModel

__all__ = [
    "SymbolModel",
    "SignalModel",
    "TradeModel",
    "TradeFeatureModel",
    "PerformanceSnapshotModel",
]
