"""
QuantPulse – Database Package
==============================
Módulo de gestión de base de datos MySQL.

ESTRUCTURA:
    db/
    ├── __init__.py         # Este archivo
    ├── migrate.py          # Runner de migraciones
    └── migrations/         # Archivos SQL
        └── 001_initial_schema.sql

COMANDOS:
    # Ejecutar migraciones
    python -m db.migrate
    
    # Reset completo
    python -m db.migrate --reset
    
    # Verificar pendientes
    python -m db.migrate --check
"""
