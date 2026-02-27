"""
QuantPulse – SQLAlchemy ORM Base Configuration
================================================
Configuración base para todos los modelos ORM.

Clean Architecture: Esta es la implementación concreta de la infraestructura
de base de datos. Los repositorios dependen de interfaces, no de esta clase.
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr

from backend.shared.config.settings import Settings

# ─── Naming Convention (para migraciones consistentes) ─────────────────────
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Base declarativa para todos los modelos ORM.
    
    Convenciones:
    - Tablename automático: CamelCase → snake_case
    - __table_args__ heredable para defaults
    """
    
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Convierte ClassName a class_name automáticamente."""
        name = cls.__name__
        # CamelCase to snake_case
        result = [name[0].lower()]
        for char in name[1:]:
            if char.isupper():
                result.append("_")
                result.append(char.lower())
            else:
                result.append(char)
        return "".join(result) + "s"  # Pluralizar


class DatabaseManager:
    """
    Manager singleton para conexión a MySQL async.
    
    USO:
        db = DatabaseManager()
        await db.initialize()  # En startup de FastAPI
        
        async with db.session() as session:
            result = await session.execute(...)
        
        await db.close()  # En shutdown de FastAPI
    """
    
    _instance: Optional["DatabaseManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, settings: Optional[Settings] = None):
        if self._initialized:
            return
        
        self._settings = settings or Settings()
        self._engine = None
        self._session_factory = None
        self._initialized = True
    
    @property
    def database_url(self) -> str:
        """Construye URL de conexión desde settings."""
        s = self._settings
        return (
            f"mysql+aiomysql://{s.db_user}:{s.db_password}"
            f"@{s.db_host}:{s.db_port}/{s.db_name}"
            f"?charset=utf8mb4"
        )
    
    async def initialize(self) -> None:
        """
        Inicializa el engine async y session factory.
        """
        if self._engine is not None:
            return
        
        s = self._settings
        self._engine = create_async_engine(
            self.database_url,
            echo=s.db_echo,
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    
    async def close(self) -> None:
        """Cierra el engine y todas las conexiones del pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
    
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager async para sesiones."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager no inicializado. Llama a initialize() primero.")
        
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    
    def get_session(self) -> AsyncSession:
        """Obtiene una sesión sin context manager."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager no inicializado.")
        return self._session_factory()


# ─── Singleton global ────────────────────────────────────────────────────
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(settings: Optional[Settings] = None) -> DatabaseManager:
    """Obtiene la instancia global del DatabaseManager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(settings)
    return _db_manager


def get_session() -> AsyncSession:
    """Helper para obtener una sesión rápidamente."""
    return get_db_manager().get_session()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para FastAPI."""
    async with get_db_manager().session() as session:
        yield session
