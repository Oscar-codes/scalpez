"""Domain repository interfaces (ABCs)."""
from backend.domain.repositories.signal_repository import ISignalRepository
from backend.domain.repositories.trade_repository import ITradeRepository

__all__ = ["ISignalRepository", "ITradeRepository"]
