"""
QuantPulse – Logging configuration
====================================
Configura logging estructurado con formato legible para desarrollo
y JSON-ready para producción futura.

NOTA: Este archivo se mueve de app/core/ a shared/logging/ como parte
de la reestructuración Clean Architecture.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configura el root logger una sola vez al arranque."""
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    # Evitar handlers duplicados si se llama más de una vez
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)

    # Silenciar librerías ruidosas
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Fábrica de loggers con namespace prefijado."""
    return logging.getLogger(f"quantpulse.{name}")
