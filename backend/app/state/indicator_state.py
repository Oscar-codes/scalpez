"""
QuantPulse – Indicator State Management
=========================================
Almacena el estado incremental de los indicadores técnicos POR SÍMBOLO.

DISEÑO:
- Cada símbolo tiene su propio SymbolIndicatorState (dataclass mutable).
- El estado contiene SOLO los valores mínimos necesarios para la
  actualización incremental O(1): último EMA, avg gain/loss, warmup counter.
- NO se almacenan series históricas de indicadores aquí; eso es responsabilidad
  del MarketState (buffer de velas) si se necesita en el futuro.

POR QUÉ NO VARIABLES GLOBALES:
- Todo estado vive dentro de IndicatorStateManager, instanciado una sola vez
  en main.py e inyectado donde se necesite.
- Testeable, sin side-effects, fácil de resetear.

WARM-UP PERIOD:
- EMA necesita al menos `period` velas antes de ser confiable.
  Antes de eso se usa SMA como seed.
- RSI necesita `period` velas para el primer cálculo (método Wilder).
- El campo `warmup_count` rastrea cuántas velas se han procesado.
- Los indicadores reportan None hasta completar el warm-up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from backend.app.core.logging import get_logger

logger = get_logger("indicator_state")

# Períodos estándar de los indicadores
EMA_FAST_PERIOD = 9
EMA_SLOW_PERIOD = 21
RSI_PERIOD = 14

# El warm-up mínimo es el mayor período requerido (EMA 21) + 1.
# +1 porque el seed de EMA 21 ocurre EXACTAMENTE en la vela 21,
# y necesitamos una vela adicional para la primera actualización
# incremental completa de todos los indicadores.
# RSI seed ocurre en la vela 15 (period+1), así que ya está listo.
MIN_WARMUP = max(EMA_SLOW_PERIOD, RSI_PERIOD) + 1


@dataclass
class SymbolIndicatorState:
    """
    Estado incremental de indicadores para UN símbolo.

    Todos los campos son Optional hasta completar el warm-up.
    Después del warm-up, se actualizan en O(1) por vela cerrada.
    """

    symbol: str

    # ─── Warm-up tracking ───────────────────────────────────────────
    warmup_count: int = 0  # Velas procesadas hasta ahora

    # ─── EMA 9 (fast) ──────────────────────────────────────────────
    # Almacena solo el último valor. O(1) para actualizar.
    ema_fast: Optional[float] = None       # Último EMA 9
    ema_fast_period: int = EMA_FAST_PERIOD

    # ─── EMA 21 (slow) ─────────────────────────────────────────────
    ema_slow: Optional[float] = None       # Último EMA 21
    ema_slow_period: int = EMA_SLOW_PERIOD

    # ─── RSI 14 (Wilder's smoothed) ────────────────────────────────
    rsi: Optional[float] = None            # Último RSI
    rsi_period: int = RSI_PERIOD
    avg_gain: Optional[float] = None       # Promedio suavizado de ganancias
    avg_loss: Optional[float] = None       # Promedio suavizado de pérdidas
    prev_close: Optional[float] = None     # Close de la vela anterior (para delta)

    # ─── Buffers temporales de warm-up ──────────────────────────────
    # Solo se usan durante el warm-up y se vacían después para liberar memoria.
    _warmup_closes: list[float] = field(default_factory=list)

    @property
    def is_warmed_up(self) -> bool:
        """¿Se completó el período de warm-up para TODOS los indicadores?"""
        return self.warmup_count >= MIN_WARMUP

    @property
    def ema_fast_ready(self) -> bool:
        """¿EMA fast listo?"""
        return self.warmup_count >= self.ema_fast_period

    @property
    def ema_slow_ready(self) -> bool:
        """¿EMA slow listo?"""
        return self.warmup_count >= self.ema_slow_period

    @property
    def rsi_ready(self) -> bool:
        """¿RSI listo? Necesita period+1 velas (period deltas)."""
        return self.warmup_count > self.rsi_period

    def to_dict(self) -> dict:
        """Serialización para API / WebSocket."""
        return {
            "symbol": self.symbol,
            "warmup_count": self.warmup_count,
            "is_warmed_up": self.is_warmed_up,
            "ema_9": round(self.ema_fast, 5) if self.ema_fast is not None else None,
            "ema_21": round(self.ema_slow, 5) if self.ema_slow is not None else None,
            "rsi_14": round(self.rsi, 2) if self.rsi is not None else None,
        }


class IndicatorStateManager:
    """
    Gestor centralizado del estado de indicadores para todos los símbolos.

    Acceso: indicator_state.get_or_create(symbol) → SymbolIndicatorState
    """

    def __init__(self) -> None:
        self._states: Dict[str, SymbolIndicatorState] = {}

    def get_or_create(self, symbol: str) -> SymbolIndicatorState:
        """Obtener estado de indicadores de un símbolo; crearlo si no existe."""
        if symbol not in self._states:
            self._states[symbol] = SymbolIndicatorState(symbol=symbol)
            logger.info(
                "IndicatorState creado para '%s' (warmup requerido: %d velas)",
                symbol,
                MIN_WARMUP,
            )
        return self._states[symbol]

    def get(self, symbol: str) -> Optional[SymbolIndicatorState]:
        """Obtener estado sin crear. Retorna None si no existe."""
        return self._states.get(symbol)

    def snapshot(self) -> dict:
        """Snapshot de todos los indicadores para diagnóstico / API."""
        return {
            symbol: state.to_dict()
            for symbol, state in self._states.items()
        }

    def get_all_symbols(self) -> list[str]:
        return list(self._states.keys())
