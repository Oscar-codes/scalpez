"""
QuantPulse – Domain Exceptions
================================
Excepciones específicas del dominio de negocio.

Estas excepciones capturan errores de lógica de negocio,
NO errores técnicos (esos van en infrastructure).

JERARQUÍA:
    DomainError (base)
    ├── InvalidSignalError
    ├── InvalidTradeError
    ├── InsufficientDataError
    ├── RiskManagementError
    └── ValidationError
"""

from __future__ import annotations


class DomainError(Exception):
    """Excepción base para errores de dominio."""
    
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)
    
    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
        }


class InvalidSignalError(DomainError):
    """Error cuando una señal no cumple los requisitos de negocio."""
    
    def __init__(self, message: str, reason: str = None):
        super().__init__(message, code="INVALID_SIGNAL")
        self.reason = reason


class InvalidTradeError(DomainError):
    """Error cuando un trade tiene datos inválidos o transición ilegal."""
    
    def __init__(self, message: str, trade_id: str = None):
        super().__init__(message, code="INVALID_TRADE")
        self.trade_id = trade_id


class InsufficientDataError(DomainError):
    """Error cuando no hay suficientes datos para un cálculo."""
    
    def __init__(self, message: str, required: int = None, available: int = None):
        super().__init__(message, code="INSUFFICIENT_DATA")
        self.required = required
        self.available = available


class RiskManagementError(DomainError):
    """Error cuando se viola una regla de gestión de riesgo."""
    
    def __init__(self, message: str, rule: str = None):
        super().__init__(message, code="RISK_VIOLATION")
        self.rule = rule


class ValidationError(DomainError):
    """Error de validación general de datos de dominio."""
    
    def __init__(self, message: str, field: str = None, value: any = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field
        self.value = value
