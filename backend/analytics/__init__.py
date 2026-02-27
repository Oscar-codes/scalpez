"""
Analytics Bounded Context
==========================
Gestiona cálculo de estadísticas y métricas de rendimiento.

Componentes:
- domain/: Entidades de dominio (PerformanceMetrics)
- services/: Servicios (StatsEngine)
"""

from backend.analytics.services.stats_engine import StatsEngine

__all__ = [
    "StatsEngine",
]
