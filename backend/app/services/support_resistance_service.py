"""
QuantPulse – Support & Resistance Service
============================================
Detección incremental de soportes y resistencias dinámicos
a partir de swing highs/lows del buffer de velas.

═══════════════════════════════════════════════════════════════
         DETECCIÓN DE SWING HIGHS / SWING LOWS
═══════════════════════════════════════════════════════════════

PATRÓN DE 3 VELAS (pivot point):

  Swing High → candle[i] es swing high si:
      candle[i].high > candle[i-1].high  (más alto que la izquierda)
      AND candle[i].high > candle[i+1].high  (más alto que la derecha)

  Swing Low → candle[i] es swing low si:
      candle[i].low < candle[i-1].low  (más bajo que la izquierda)
      AND candle[i].low < candle[i+1].low  (más bajo que la derecha)

CÓMO SE DETECTA SIN "MIRAR AL FUTURO" (anti-repainting):
  No podemos saber si candle[i] es swing hasta que candle[i+1] cierre.
  Por eso, cada vez que una vela nueva cierra, evaluamos si la vela
  ANTERIOR (candle[-2] en el buffer) fue un swing.

  Buffer actualizado:
    [..., candle[-3], candle[-2], candle[-1]]
                         ↑ candidata   ↑ recién cerrada

  Comparamos candle[-2] con sus vecinos candle[-3] y candle[-1].
  Esto cuesta O(1) por evaluación – solo inspecciona 3 posiciones.

POR QUÉ 3 VELAS Y NO 5:
  En scalping con velas de 5 segundos, usar 5 velas requiere esperar
  25 segundos para confirmar un swing. Con 3 velas son solo 15s,
  lo cual captura micro-movimientos sin demasiado lag.

═══════════════════════════════════════════════════════════════
         SOPORTE Y RESISTENCIA DINÁMICOS
═══════════════════════════════════════════════════════════════

SOPORTE: Clúster de swing lows recientes por debajo del precio actual.
  → "Piso" donde el precio tiende a rebotar.

RESISTENCIA: Clúster de swing highs recientes por encima del precio actual.
  → "Techo" donde el precio tiende a ser rechazado.

Se mantienen en deque(maxlen=N) → los niveles obsoletos se descartan
automáticamente al llegar nuevos.

═══════════════════════════════════════════════════════════════
         FILTRO DE CONSOLIDACIÓN
═══════════════════════════════════════════════════════════════

Un mercado consolidando tiene:
  total_range ≈ rango promedio de una sola vela.

  total_range = max(high, N velas) - min(low, N velas)
  avg_candle_range = promedio(high - low) de las últimas N velas

  Si total_range < avg_candle_range × multiplier → consolidación → NO operar.

Esto evita señales en rangos estrechos sin dirección clara.

═══════════════════════════════════════════════════════════════
         DETECCIÓN DE RUPTURAS (BREAKOUTS)
═══════════════════════════════════════════════════════════════

Ruptura alcista:
  close > resistencia Y candle_range > avg_range × mult
  → El precio rompió el techo con fuerza (vela grande).

Ruptura bajista:
  close < soporte Y candle_range > avg_range × mult
  → El precio rompió el piso con fuerza.

El multiplicador asegura que la vela de ruptura es significativamente
más grande que el promedio, descartando rupturas débiles/falsas.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from backend.app.core.logging import get_logger
from backend.app.domain.entities.candle import Candle

logger = get_logger("support_resistance")


@dataclass
class SymbolSRState:
    """Estado de soportes/resistencias para UN símbolo."""

    symbol: str
    # deque de (precio, timestamp) → los más recientes al final
    swing_highs: deque = field(default_factory=lambda: deque(maxlen=10))
    swing_lows: deque = field(default_factory=lambda: deque(maxlen=10))


class SupportResistanceService:
    """
    Servicio de detección incremental de soportes y resistencias.

    Ciclo de vida:
      1. Se instancia una vez en main.py.
      2. ProcessTickUseCase llama a update() por cada vela cerrada.
      3. SignalEngine consulta niveles S/R y condiciones.

    Complejidad: O(1) por actualización (inspección de 3 velas).
    Consultas: O(K) donde K = número de niveles almacenados (max 10).
    """

    def __init__(
        self,
        *,
        max_levels: int = 10,
        sr_tolerance_pct: float = 0.0015,
        breakout_candle_mult: float = 1.2,
        consolidation_candles: int = 10,
        consolidation_atr_mult: float = 2.0,
    ) -> None:
        self._max_levels = max_levels
        self._sr_tolerance_pct = sr_tolerance_pct
        self._breakout_candle_mult = breakout_candle_mult
        self._consolidation_candles = consolidation_candles
        self._consolidation_atr_mult = consolidation_atr_mult
        self._states: Dict[str, SymbolSRState] = {}

        logger.info(
            "SupportResistanceService inicializado "
            "(max_levels=%d, tolerance=%.4f, breakout_mult=%.2f, "
            "consol_candles=%d, consol_atr_mult=%.2f)",
            max_levels, sr_tolerance_pct, breakout_candle_mult,
            consolidation_candles, consolidation_atr_mult,
        )

    # ════════════════════════════════════════════════════════════════
    #  ESTADO POR SÍMBOLO
    # ════════════════════════════════════════════════════════════════

    def _get_state(self, symbol: str) -> SymbolSRState:
        """Obtener o crear estado S/R para un símbolo."""
        if symbol not in self._states:
            self._states[symbol] = SymbolSRState(
                symbol=symbol,
                swing_highs=deque(maxlen=self._max_levels),
                swing_lows=deque(maxlen=self._max_levels),
            )
        return self._states[symbol]

    # ════════════════════════════════════════════════════════════════
    #  ACTUALIZACIÓN INCREMENTAL (llamar en cada vela cerrada)
    # ════════════════════════════════════════════════════════════════

    def update(self, candle: Candle, candles_buffer: deque) -> None:
        """
        Evaluar si la vela anterior (candle[-2]) es un swing point.

        CÓMO SE EVITA REPAINTING:
        - Solo se evalúa candle[-2] cuando candle[-1] ya cerró.
        - El swing se confirma con datos pasados, nunca con la vela actual
          en construcción.

        Complejidad: O(1) — solo inspecciona 3 posiciones del buffer.
        """
        if len(candles_buffer) < 3:
            return

        state = self._get_state(candle.symbol)

        # Buffer: [-3]=izquierda, [-2]=candidata a swing, [-1]=recién cerrada
        left = candles_buffer[-3]
        pivot = candles_buffer[-2]
        right = candles_buffer[-1]  # = candle (la recién cerrada)

        # ── Detectar Swing High (resistencia potencial) ──
        # La vela central tiene un high mayor que ambos vecinos.
        if pivot.high > left.high and pivot.high > right.high:
            state.swing_highs.append((pivot.high, pivot.timestamp))
            logger.debug(
                "Swing High [%s] @ %.5f (ts=%.0f)",
                candle.symbol, pivot.high, pivot.timestamp,
            )

        # ── Detectar Swing Low (soporte potencial) ──
        # La vela central tiene un low menor que ambos vecinos.
        if pivot.low < left.low and pivot.low < right.low:
            state.swing_lows.append((pivot.low, pivot.timestamp))
            logger.debug(
                "Swing Low [%s] @ %.5f (ts=%.0f)",
                candle.symbol, pivot.low, pivot.timestamp,
            )

    # ════════════════════════════════════════════════════════════════
    #  CONSULTAS DE NIVELES S/R
    # ════════════════════════════════════════════════════════════════

    def get_nearest_support(self, symbol: str, price: float) -> Optional[float]:
        """
        Soporte más cercano POR DEBAJO del precio actual.

        Busca entre los swing lows almacenados el que esté más cerca
        del precio actual pero por debajo.

        Complejidad: O(K) donde K ≤ max_levels (constante = 10).
        """
        state = self._get_state(symbol)
        supports_below = [s for s, _ in state.swing_lows if s < price]
        if not supports_below:
            return None
        return max(supports_below)  # El más cercano por debajo

    def get_nearest_resistance(self, symbol: str, price: float) -> Optional[float]:
        """
        Resistencia más cercana POR ENCIMA del precio actual.

        Complejidad: O(K) donde K ≤ max_levels (constante = 10).
        """
        state = self._get_state(symbol)
        resistances_above = [r for r, _ in state.swing_highs if r > price]
        if not resistances_above:
            return None
        return min(resistances_above)  # El más cercano por encima

    def get_last_swing_low(self, symbol: str) -> Optional[float]:
        """Último swing low detectado (para Stop Loss de señales BUY)."""
        state = self._get_state(symbol)
        if not state.swing_lows:
            return None
        return state.swing_lows[-1][0]

    def get_last_swing_high(self, symbol: str) -> Optional[float]:
        """Último swing high detectado (para Stop Loss de señales SELL)."""
        state = self._get_state(symbol)
        if not state.swing_highs:
            return None
        return state.swing_highs[-1][0]

    # ════════════════════════════════════════════════════════════════
    #  CONDICIONES DE TRADING
    # ════════════════════════════════════════════════════════════════

    def is_bounce_on_support(
        self, candle: Candle, support: Optional[float],
    ) -> bool:
        """
        ¿La vela rebotó en un soporte confirmado?

        CÓMO SE DETECTA REBOTE:
        1. El low de la vela se acercó al soporte (dentro de tolerancia %).
        2. El close quedó POR ENCIMA del soporte (no rompió).
        3. La vela es alcista (close > open → compradores ganaron).

        La tolerancia % adapta la detección a cualquier escala de precio
        (funciona igual para R_100 @ 825 que para R_75 @ 37000).
        """
        if support is None:
            return False

        tolerance = support * self._sr_tolerance_pct
        near_support = candle.low <= support + tolerance
        held_above = candle.close > support
        bullish = candle.close > candle.open

        return near_support and held_above and bullish

    def is_rejection_at_resistance(
        self, candle: Candle, resistance: Optional[float],
    ) -> bool:
        """
        ¿La vela fue rechazada en una resistencia confirmada?

        CÓMO SE DETECTA RECHAZO:
        1. El high de la vela se acercó a la resistencia (dentro de tolerancia %).
        2. El close quedó POR DEBAJO de la resistencia (no rompió).
        3. La vela es bajista (close < open → vendedores ganaron).
        """
        if resistance is None:
            return False

        tolerance = resistance * self._sr_tolerance_pct
        near_resistance = candle.high >= resistance - tolerance
        held_below = candle.close < resistance
        bearish = candle.close < candle.open

        return near_resistance and held_below and bearish

    def is_breakout_above(
        self, candle: Candle, resistance: Optional[float], avg_range: float,
    ) -> bool:
        """
        ¿Ruptura alcista por encima de resistencia?

        CÓMO SE CONFIRMA RUPTURA:
        1. Close por encima de la resistencia (rompió el techo).
        2. Rango de la vela > promedio × multiplicador (vela de fuerza).

        El multiplicador asegura que no es un "fake breakout" con
        una vela pequeña que apenas pasa el nivel.
        """
        if resistance is None or avg_range <= 0:
            return False

        candle_range = candle.high - candle.low
        broke_above = candle.close > resistance
        strong_candle = candle_range > avg_range * self._breakout_candle_mult

        return broke_above and strong_candle

    def is_breakout_below(
        self, candle: Candle, support: Optional[float], avg_range: float,
    ) -> bool:
        """
        ¿Ruptura bajista por debajo de soporte?

        1. Close por debajo del soporte (rompió el piso).
        2. Rango de la vela > promedio × multiplicador (vela de fuerza).
        """
        if support is None or avg_range <= 0:
            return False

        candle_range = candle.high - candle.low
        broke_below = candle.close < support
        strong_candle = candle_range > avg_range * self._breakout_candle_mult

        return broke_below and strong_candle

    # ════════════════════════════════════════════════════════════════
    #  FILTROS DE MERCADO
    # ════════════════════════════════════════════════════════════════

    def is_consolidating(self, candles_buffer: deque) -> bool:
        """
        ¿El mercado está en consolidación (rango estrecho)?

        CÓMO SE FILTRA:
        1. Calcular rango total de las últimas N velas:
              total_range = max(high) - min(low)
        2. Calcular rango promedio por vela:
              avg_range = promedio(high - low)
        3. Si total_range < avg_range × multiplier → consolidación.

        LÓGICA:
        En un mercado con tendencia, el total_range es mucho mayor que
        el rango de una vela individual. En consolidación, el precio se
        mueve dentro de un rango similar al de una vela → sin dirección.

        Complejidad: O(N) donde N = consolidation_candles (constante = 10).
        """
        n = self._consolidation_candles
        recent = list(candles_buffer)[-n:]

        if len(recent) < n:
            return True  # Sin suficientes datos → conservador → no operar

        highs = [c.high for c in recent]
        lows = [c.low for c in recent]

        total_range = max(highs) - min(lows)
        avg_candle_range = sum(h - l for h, l in zip(highs, lows)) / n

        if avg_candle_range == 0:
            return True  # Sin movimiento → consolidación

        return total_range < avg_candle_range * self._consolidation_atr_mult

    def compute_avg_range(self, candles_buffer: deque, period: int = 10) -> float:
        """
        Promedio del rango (high - low) de las últimas N velas.
        Se usa para evaluar si una vela de ruptura es "fuerte".

        Complejidad: O(N) donde N = period (constante = 10).
        """
        recent = list(candles_buffer)[-period:]
        if not recent:
            return 0.0
        return sum(c.high - c.low for c in recent) / len(recent)

    # ════════════════════════════════════════════════════════════════
    #  DIAGNÓSTICO / API
    # ════════════════════════════════════════════════════════════════

    def get_levels(self, symbol: str) -> dict:
        """Snapshot de niveles S/R para API / debug."""
        state = self._get_state(symbol)
        return {
            "symbol": symbol,
            "swing_highs": [
                {"price": round(p, 5), "timestamp": ts}
                for p, ts in state.swing_highs
            ],
            "swing_lows": [
                {"price": round(p, 5), "timestamp": ts}
                for p, ts in state.swing_lows
            ],
            "total_highs": len(state.swing_highs),
            "total_lows": len(state.swing_lows),
        }

    def get_all_levels(self) -> dict:
        """Snapshot de todos los símbolos."""
        return {
            symbol: self.get_levels(symbol)
            for symbol in self._states
        }
