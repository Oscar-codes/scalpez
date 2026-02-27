"""
QuantPulse – Repositories Package
==================================
Repositorios async para persistencia en MySQL.

USO:
    from backend.app.infrastructure.repositories import SignalRepository, TradeRepository
    
    async with db_manager.session() as session:
        signal_repo = SignalRepository(session)
        trade_repo = TradeRepository(session)
        
        signal_id = await signal_repo.save(signal, indicators)
        trade_id = await trade_repo.save(trade, signal_id)
        
        await session.commit()
"""

from backend.app.infrastructure.repositories.signal_repository import SignalRepository
from backend.app.infrastructure.repositories.trade_repository import TradeRepository

__all__ = ["SignalRepository", "TradeRepository"]
