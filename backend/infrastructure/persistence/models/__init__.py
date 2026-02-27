"""
Infrastructure Models Package.

Contiene los modelos ORM de SQLAlchemy para la persistencia.
Estos modelos representan la estructura de la base de datos,
NO las entidades de dominio.
"""

# Re-export desde la ubicación legacy para compatibilidad
from backend.app.infrastructure.models.signal import SignalModel
from backend.app.infrastructure.models.trade import TradeModel
from backend.app.infrastructure.models.symbol import SymbolModel
from backend.app.infrastructure.models.trade_features import TradeFeatureModel
from backend.app.infrastructure.models.performance import PerformanceModel

__all__ = [
    "SignalModel",
    "TradeModel", 
    "SymbolModel",
    "TradeFeatureModel",
    "PerformanceModel",
]
