"""
QuantPulse – Application Layer
================================
Capa de casos de uso y orquestación.

Este módulo contiene:
- use_cases/: Casos de uso (orquestradores de dominio)
- ports/: Interfaces hacia infraestructura
- dto/: Data Transfer Objects
- services/: Application services de orquestación

REGLA DE DEPENDENCIA:
Esta capa puede importar de:
- domain/ (entidades, servicios, interfaces)
- ports/ propios (interfaces hacia infra)

NO puede importar de:
- infrastructure/ (implementaciones concretas)
- presentation/ (API)
"""

from backend.application.use_cases.generate_signal_usecase import (
    GenerateSignalUseCase,
    GenerateSignalResult,
)
from backend.application.use_cases.process_tick_usecase import (
    ProcessTickUseCase,
    ProcessTickResult,
)

__all__ = [
    "ProcessTickUseCase",
    "ProcessTickResult",
    "GenerateSignalUseCase",
    "GenerateSignalResult",
]
