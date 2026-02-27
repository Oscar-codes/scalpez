"""Re-export from shared domain (backward compatibility)."""
from backend.shared.domain.entities.trade import SimulatedTrade, TradeStatus

__all__ = ["SimulatedTrade", "TradeStatus"]
