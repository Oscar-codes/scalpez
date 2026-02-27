"""
QuantPulse – Domain Entity: Signal
=====================================
Señal de trading inmutable generada por el Signal Engine.

DECISIONES DE DISEÑO:
- frozen=True → inmutable una vez generada, EVITA REPAINTING.
  Nadie puede alterar una señal emitida retroactivamente.
- conditions es tuple (inmutable) → registro auditable de qué
  condiciones activaron la señal.
- Se genera SOLO en vela cerrada → no hay señales provisionales.

CAMPOS:
- id:               Identificador único compacto (UUID hex 12 chars)
- symbol:           Par/instrumento (e.g. "R_100")
- signal_type:      "BUY" o "SELL"
- entry:            Precio de entrada (close de la vela confirmada)
- stop_loss:        Nivel de stop loss técnico
- take_profit:      Nivel de take profit basado en RR
- rr:               Ratio riesgo/recompensa real calculado
- timestamp:        Momento de generación (epoch)
- candle_timestamp: Timestamp de la vela que confirmó la señal
- conditions:       Tupla de strings con las condiciones activadas
- confidence:       Número de condiciones confirmadas (2–5)
- estimated_duration: Duración estimada en segundos (INFORMATIVO, no filtra)

PREPARADO PARA:
- Trade Simulator (Fase 4): Signal → SimulatedTrade
- Persistencia futura: Signal.to_dict() → JSON → DB
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Signal:
    """Señal de trading inmutable con gestión de riesgo pre-calculada."""

    id: str
    symbol: str
    signal_type: str         # "BUY" | "SELL"
    entry: float
    stop_loss: float
    take_profit: float
    rr: float                # Risk-Reward real
    timestamp: float         # epoch de generación
    candle_timestamp: float  # epoch de la vela confirmante
    conditions: tuple        # ("ema_cross", "rsi_reversal", ...) inmutable
    confidence: int          # len(conditions)
    estimated_duration: float = 0.0  # Duración estimada en segundos (INFORMATIVO)
    ml_probability: float = None     # Probabilidad ML de éxito (0.0-1.0), None si ML deshabilitado

    def to_dict(self) -> dict:
        """Serialización para API / WebSocket / persistencia futura."""
        result = {
            "id": self.id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "entry": round(self.entry, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5),
            "rr": round(self.rr, 2),
            "timestamp": self.timestamp,
            "candle_timestamp": self.candle_timestamp,
            "conditions": list(self.conditions),
            "confidence": self.confidence,
            "estimated_duration": round(self.estimated_duration, 1),
        }
        # Incluir ml_probability solo si está disponible
        if self.ml_probability is not None:
            result["ml_probability"] = round(self.ml_probability, 4)
        return result

    @staticmethod
    def generate_id() -> str:
        """ID compacto único (12 chars hex de UUID4)."""
        return uuid.uuid4().hex[:12]
