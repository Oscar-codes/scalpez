"""
QuantPulse – SQLAlchemy ORM Base Configuration
================================================
Configuración base para todos los modelos ORM.

DECISIONES DE DISEÑO:

1. ASYNC ENGINE:
   - Usamos sqlalchemy[asyncio] + aiomysql para no bloquear el event loop.
   - Crítico para alta frecuencia: un SELECT síncrono bloquearía ticks.

2. SESSION FACTORY:
   - AsyncSession con expire_on_commit=False para evitar queries
     automáticas post-commit que bloquean.

3. NAMING CONVENTION:
   - Convención explícita para índices y FKs.
   - Facilita migraciones y debugging.

4. TIPO DECIMAL CON APDAPTER:
   - TypeDecorator para DECIMAL que maneja precisión de trading.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr

from backend.app.core.settings import settings

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
    
    POR QUÉ ASYNC:
        Un query síncrono de 10ms bloquea 10ms de ticks.
        Con async, el event loop procesa otros eventos mientras espera I/O.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._engine = None
        self._session_factory = None
        self._initialized = True
    
    @property
    def database_url(self) -> str:
        """Construye URL de conexión desde settings."""
        return (
            f"mysql+aiomysql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
            f"?charset=utf8mb4"
        )
    
    async def initialize(self) -> None:
        """
        Inicializa el engine async y session factory.
        
        POOL SIZING:
        - pool_size=5: Conexiones persistentes en el pool.
        - max_overflow=10: Conexiones extra en picos de carga.
        - pool_recycle=3600: Recicla conexiones cada hora (evita timeouts MySQL).
        - pool_pre_ping=True: Verifica conexión antes de usarla (detecta desconexiones).
        """
        if self._engine is not None:
            return
        
        self._engine = create_async_engine(
            self.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Evita queries automáticas post-commit
            autoflush=False,         # Control explícito de flush
        )
    
    async def close(self) -> None:
        """Cierra el engine y todas las conexiones del pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
    
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager async para sesiones.
        
        USO:
            async with db.session() as session:
                await session.execute(...)
                await session.commit()
        
        TRANSACCIONES:
        - Commit es explícito (no autocommit).
        - Rollback automático en excepciones dentro del context.
        """
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager no inicializado. Llama a initialize() primero.")
        
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    
    def get_session(self) -> AsyncSession:
        """
        Obtiene una sesión sin context manager.
        El caller es responsable de commit/rollback/close.
        """
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager no inicializado. Llama a initialize() primero.")
        return self._session_factory()


# ─── Singleton global ────────────────────────────────────────────────────
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para FastAPI.
    
    USO en routes:
        @router.get("/trades")
        async def get_trades(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with db_manager.session() as session:
        yield session
