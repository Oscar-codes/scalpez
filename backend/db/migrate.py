"""
QuantPulse – Database Migration Runner
=======================================
Script para ejecutar migraciones SQL en MySQL.

USO:
    # Desde el directorio backend/
    python -m db.migrate
    
    # O con opciones
    python -m db.migrate --reset  # Dropear y recrear todo
    python -m db.migrate --seed   # Insertar datos de prueba

ESTRUCTURA DE MIGRACIONES:
    db/migrations/
    ├── 001_initial_schema.sql
    ├── 002_add_indexes.sql
    └── ...

Las migraciones se ejecutan en orden numérico y se trackean
en una tabla __migrations para no re-ejecutar.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Agregar el directorio backend al path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import aiomysql

from app.core.settings import settings
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("db.migrate")


# ─── Configuración ────────────────────────────────────────────────────────
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_connection():
    """Obtiene una conexión directa a MySQL (sin ORM)."""
    return await aiomysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
        charset="utf8mb4",
        autocommit=False,
    )


async def ensure_database():
    """Crea la base de datos si no existe."""
    conn = await aiomysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        charset="utf8mb4",
    )
    
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            await conn.commit()
            logger.info(f"Base de datos '{settings.db_name}' verificada/creada")
    finally:
        conn.close()


async def ensure_migrations_table(conn):
    """Crea la tabla de tracking de migraciones si no existe."""
    async with conn.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS `__migrations` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `name` VARCHAR(255) NOT NULL UNIQUE,
                `executed_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """)
        await conn.commit()


async def get_executed_migrations(conn) -> set:
    """Obtiene las migraciones ya ejecutadas."""
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT name FROM __migrations")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


async def mark_migration_executed(conn, name: str):
    """Marca una migración como ejecutada."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            "INSERT INTO __migrations (name) VALUES (%s)", (name,)
        )


async def execute_sql_file(conn, filepath: Path):
    """Ejecuta un archivo SQL completo."""
    sql_content = filepath.read_text(encoding="utf-8")
    
    # Dividir por ';' pero ignorar los que están dentro de strings/comentarios
    # Para simplicidad, usamos una división básica
    statements = []
    current = []
    
    for line in sql_content.split("\n"):
        stripped = line.strip()
        
        # Ignorar comentarios de línea completa
        if stripped.startswith("--") or stripped.startswith("#"):
            continue
        
        current.append(line)
        
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt and not stmt.startswith("--"):
                statements.append(stmt)
            current = []
    
    # Ejecutar cada statement
    async with conn.cursor() as cursor:
        for stmt in statements:
            # Ignorar statements vacíos o solo comentarios
            clean = stmt.strip()
            if not clean or clean == ";":
                continue
            
            try:
                await cursor.execute(stmt)
            except Exception as e:
                # Ignorar errores de "already exists" para idempotencia
                err_str = str(e).lower()
                if "already exists" in err_str or "duplicate" in err_str:
                    logger.debug(f"Ignorando (ya existe): {stmt[:50]}...")
                    continue
                raise


async def run_migrations(reset: bool = False, seed: bool = False):
    """
    Ejecuta todas las migraciones pendientes.
    
    Args:
        reset: Si True, dropea todas las tablas primero
        seed: Si True, inserta datos de prueba después
    """
    # Asegurar que la BD existe
    await ensure_database()
    
    conn = await get_connection()
    
    try:
        if reset:
            logger.warning("⚠️ Reseteando base de datos...")
            async with conn.cursor() as cursor:
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                
                # Obtener todas las tablas
                await cursor.execute("SHOW TABLES")
                tables = [row[0] for row in await cursor.fetchall()]
                
                for table in tables:
                    await cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
                    logger.info(f"  Dropped: {table}")
                
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                await conn.commit()
        
        # Asegurar tabla de tracking
        await ensure_migrations_table(conn)
        
        # Obtener migraciones ejecutadas
        executed = await get_executed_migrations(conn)
        
        # Obtener archivos de migración ordenados
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        
        if not migration_files:
            logger.warning(f"No se encontraron migraciones en {MIGRATIONS_DIR}")
            return
        
        # Ejecutar migraciones pendientes
        pending = 0
        for filepath in migration_files:
            name = filepath.name
            
            if name in executed:
                logger.debug(f"  Saltando (ya ejecutada): {name}")
                continue
            
            logger.info(f"📦 Ejecutando migración: {name}")
            
            try:
                await execute_sql_file(conn, filepath)
                await mark_migration_executed(conn, name)
                await conn.commit()
                logger.info(f"  ✅ {name} completada")
                pending += 1
            except Exception as e:
                await conn.rollback()
                logger.error(f"  ❌ Error en {name}: {e}")
                raise
        
        if pending == 0:
            logger.info("✅ No hay migraciones pendientes")
        else:
            logger.info(f"✅ {pending} migraciones ejecutadas")
        
        # Seed opcional
        if seed:
            await run_seed(conn)
    
    finally:
        conn.close()


async def run_seed(conn):
    """Inserta datos de prueba."""
    logger.info("🌱 Insertando datos de seed...")
    
    seed_file = MIGRATIONS_DIR / "seed.sql"
    if seed_file.exists():
        await execute_sql_file(conn, seed_file)
        await conn.commit()
        logger.info("  ✅ Seed completado")
    else:
        logger.info("  No se encontró archivo seed.sql")


def main():
    parser = argparse.ArgumentParser(description="QuantPulse Database Migrations")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Dropear todas las tablas antes de migrar",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Insertar datos de prueba después de migrar",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo verificar migraciones pendientes sin ejecutar",
    )
    
    args = parser.parse_args()
    
    if args.check:
        asyncio.run(check_pending())
    else:
        asyncio.run(run_migrations(reset=args.reset, seed=args.seed))


async def check_pending():
    """Lista migraciones pendientes sin ejecutar."""
    await ensure_database()
    conn = await get_connection()
    
    try:
        await ensure_migrations_table(conn)
        executed = await get_executed_migrations(conn)
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        
        pending = []
        for filepath in migration_files:
            if filepath.name not in executed:
                pending.append(filepath.name)
        
        if pending:
            logger.info(f"📋 Migraciones pendientes ({len(pending)}):")
            for name in pending:
                logger.info(f"  - {name}")
        else:
            logger.info("✅ No hay migraciones pendientes")
    
    finally:
        conn.close()


if __name__ == "__main__":
    main()
