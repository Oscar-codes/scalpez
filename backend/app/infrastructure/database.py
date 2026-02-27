"""Re-export from infrastructure.persistence (backward compatibility)."""
from backend.infrastructure.persistence.database import (
    Base,
    DatabaseManager,
    db_manager,
    get_db_manager,
    get_db_session,
    get_session,
)

__all__ = [
    "Base",
    "DatabaseManager",
    "db_manager",
    "get_db_manager",
    "get_db_session",
    "get_session",
]
