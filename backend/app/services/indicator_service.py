"""
QuantPulse – Indicator Service (EMA 9, EMA 21, RSI 14)
========================================================
Motor de indicadores técnicos con cálculo INCREMENTAL O(1) por vela.

═══════════════════════════════════════════════════════════════════
                    MATEMÁTICA DETALLADA
═══════════════════════════════════════════════════════════════════

─── EMA (Exponential Moving Average) ────────────────────────────

  Fórmula recursiva:
      EMA_t = Price_t × α  +  EMA_{t-1} × (1 − α)

  Donde:
      α  (smoothing factor) = 2 / (period + 1)

  Seed (primera EMA):
      Se usa SMA (Simple Moving Average) de las primeras `period` velas
      como valor inicial. Esto es estándar en la industria y evita
      sensibilidad al primer dato.

      SMA = Σ(close_i, i=1..period) / period
      EMA_period = SMA   ← seed
      EMA_{period+1} = close_{period+1} × α + SMA × (1 − α)
      ...y recursivamente en adelante.

  Complejidad: O(1) por actualización después del seed.

─── RSI (Relative Strength Index) – Método Wilder ──────────────

  Paso 1 – Calcular deltas:
      delta_t = close_t − close_{t-1}
      gain_t  = max(delta_t, 0)
      loss_t  = |min(delta_t, 0)|  (siempre positivo)

  Paso 2 – Primer promedio (SMA de las primeras `period` deltas):
      avg_gain_initial = Σ(gain_i, i=1..period) / period
      avg_loss_initial = Σ(loss_i, i=1..period) / period

  Paso 3 – Suavizado de Wilder (EMA-like con α = 1/period):
      avg_gain_t = (avg_gain_{t-1} × (period − 1) + gain_t) / period
      avg_loss_t = (avg_loss_{t-1} × (period − 1) + loss_t) / period

      Nota: esto es equivalente a una EMA con α = 1/period,
      que es el método original de Wilder (1978). Es MÁS suave
      que la EMA estándar con α = 2/(period+1).

  Paso 4 – RS y RSI:
      RS  = avg_gain / avg_loss
      RSI = 100 − (100 / (1 + RS))

  Edge case – División por cero:
      Si avg_loss == 0 → RSI = 100  (mercado solo sube)
      Si avg_gain == 0 → RSI = 0    (mercado solo baja)

  Complejidad: O(1) por actualización después del seed.

═══════════════════════════════════════════════════════════════════
               DECISIONES DE DISEÑO
═══════════════════════════════════════════════════════════════════

CÓMO SE EVITA REPAINTING:
- Solo se llama a update() con VELAS CERRADAS (inmutables, frozen=True).
- La vela en construcción NUNCA llega aquí.
- El estado anterior solo se modifica con datos finales.

CÓMO SE PROTEGE MEMORIA:
- El buffer de warm-up (_warmup_closes) se vacía tras completar el seed.
- Solo se almacenan escalares (último EMA, avg_gain/loss), no series.

POR QUÉ NO PANDAS / TA-LIB:
- Overhead de conversión array ↔ scalar es > 10x para O(1) incremental.
- Dependencia externa innecesaria para 3 cálculos aritméticos.
- Control total sobre edge cases y precisión numérica.

PREPARADO PARA SEÑALES:
- update() retorna un dict con todos los indicadores actualizados,
  listo para ser consumido por el futuro Signal Engine.
"""

from __future__ import annotations

from typing import Optional

from backend.app.core.logging import get_logger
from backend.app.domain.entities.candle import Candle
from backend.app.state.indicator_state import (
    IndicatorStateManager,
    SymbolIndicatorState,
)

logger = get_logger("indicator_service")


class IndicatorService:
    """
    Motor de indicadores técnicos incrementales.

    Ciclo de vida:
      1. Se instancia una vez en main.py con el IndicatorStateManager.
      2. ProcessTickUseCase llama a update() por cada vela cerrada.
      3. update() modifica SymbolIndicatorState en O(1).
      4. Retorna snapshot de indicadores para log/broadcast.

    Uso:
        result = indicator_service.update(candle)
        # result = {"ema_9": 1234.5, "ema_21": 1230.1, "rsi_14": 62.3}
        # o None si aún en warm-up
    """

    def __init__(self, state_manager: IndicatorStateManager) -> None:
        self._state_manager = state_manager

        # ─── Pre-calcular alphas (constantes, nunca cambian) ────────
        # α_fast = 2 / (9 + 1) = 0.2
        self._alpha_fast: float = 2.0 / (9 + 1)
        # α_slow = 2 / (21 + 1) ≈ 0.0909
        self._alpha_slow: float = 2.0 / (21 + 1)

        logger.info(
            "IndicatorService inicializado (EMA9 α=%.4f, EMA21 α=%.4f, RSI14 Wilder)",
            self._alpha_fast,
            self._alpha_slow,
        )

    # ════════════════════════════════════════════════════════════════
    #  PUNTO DE ENTRADA PRINCIPAL
    # ════════════════════════════════════════════════════════════════

    def update(self, candle: Candle) -> Optional[dict]:
        """
        Actualizar TODOS los indicadores para un símbolo dado una vela cerrada.

        Complejidad: O(1) amortizado.
        - Durante warm-up: O(1) append + posible O(N) seed (una sola vez).
        - Post warm-up: O(1) puro.

        Retorna:
            dict con valores actualizados si warm-up completo, None si no.
        """
        state = self._state_manager.get_or_create(candle.symbol)
        close = candle.close

        # ── Incrementar contador de warm-up ──
        state.warmup_count += 1

        # ── Fase de warm-up: acumular closes y hacer seed de indicadores ──
        if not state.is_warmed_up:
            state._warmup_closes.append(close)
            self._try_seed_indicators(state, close)
            state.prev_close = close
            return None

        # ── Transición warm-up → steady state (ocurre UNA sola vez) ──
        # En esta vela, is_warmed_up acaba de volverse True.
        # Todavía hay datos en _warmup_closes → hacer última actualización
        # incremental y luego liberar el buffer.
        if state._warmup_closes:
            state._warmup_closes.append(close)
            self._try_seed_indicators(state, close)
            state._warmup_closes.clear()  # Liberar memoria
            logger.info(
                "✓ Warm-up completo para '%s' después de %d velas: "
                "EMA9=%.5f EMA21=%.5f RSI=%.2f",
                state.symbol,
                state.warmup_count,
                state.ema_fast or 0,
                state.ema_slow or 0,
                state.rsi or 0,
            )
            state.prev_close = close
            return state.to_dict()

        # ── Steady state: actualización incremental O(1) ──
        self._update_ema_fast(state, close)
        self._update_ema_slow(state, close)
        self._update_rsi(state, close)

        state.prev_close = close

        return state.to_dict()

    # ════════════════════════════════════════════════════════════════
    #  WARM-UP / SEED
    # ════════════════════════════════════════════════════════════════

    def _try_seed_indicators(self, state: SymbolIndicatorState, close: float) -> None:
        """
        Intentar hacer seed de cada indicador cuando tenga suficientes datos.
        Cada indicador se seedea EXACTAMENTE UNA VEZ.
        """
        closes = state._warmup_closes
        count = state.warmup_count

        # ── Seed EMA 9 (necesita 9 velas) ──
        if state.ema_fast is None and count == state.ema_fast_period:
            # SMA de las primeras 9 velas como seed
            sma = sum(closes[-state.ema_fast_period:]) / state.ema_fast_period
            state.ema_fast = sma
            logger.debug("Seed EMA9 para '%s': SMA=%.5f", state.symbol, sma)

        elif state.ema_fast is not None and count > state.ema_fast_period:
            # Ya tiene seed → actualizar incrementalmente
            self._update_ema_fast(state, close)

        # ── Seed EMA 21 (necesita 21 velas) ──
        if state.ema_slow is None and count == state.ema_slow_period:
            sma = sum(closes[-state.ema_slow_period:]) / state.ema_slow_period
            state.ema_slow = sma
            logger.debug("Seed EMA21 para '%s': SMA=%.5f", state.symbol, sma)

        elif state.ema_slow is not None and count > state.ema_slow_period:
            self._update_ema_slow(state, close)

        # ── Seed RSI 14 (necesita 15 velas: 14 deltas + 1 close anterior) ──
        # Con warmup_count velas tenemos warmup_count-1 deltas.
        # RSI seed necesita rsi_period deltas → warmup_count == rsi_period + 1
        if (
            state.avg_gain is None
            and count == state.rsi_period + 1
            and len(closes) >= state.rsi_period + 1
        ):
            self._seed_rsi(state, closes)

        elif state.avg_gain is not None and count > state.rsi_period + 1:
            self._update_rsi(state, close)

    def _seed_rsi(self, state: SymbolIndicatorState, closes: list[float]) -> None:
        """
        Calcular el primer RSI usando SMA de gains/losses (método Wilder).

        Se necesitan `period` deltas, es decir `period + 1` closes.

        avg_gain_initial = Σ(gain_i) / period   para i = 1..period
        avg_loss_initial = Σ(loss_i) / period   para i = 1..period
        """
        period = state.rsi_period
        # Últimos period+1 closes → period deltas
        relevant = closes[-(period + 1):]
        total_gain = 0.0
        total_loss = 0.0

        for i in range(1, len(relevant)):
            delta = relevant[i] - relevant[i - 1]
            if delta > 0:
                total_gain += delta
            else:
                total_loss += abs(delta)

        state.avg_gain = total_gain / period
        state.avg_loss = total_loss / period

        # Calcular RSI inicial
        state.rsi = self._compute_rsi(state.avg_gain, state.avg_loss)

        logger.debug(
            "Seed RSI14 para '%s': avg_gain=%.5f avg_loss=%.5f RSI=%.2f",
            state.symbol,
            state.avg_gain,
            state.avg_loss,
            state.rsi,
        )

    # ════════════════════════════════════════════════════════════════
    #  ACTUALIZACIONES INCREMENTALES O(1)
    # ════════════════════════════════════════════════════════════════

    def _update_ema_fast(self, state: SymbolIndicatorState, close: float) -> None:
        """
        EMA 9 incremental:
            EMA_t = close × α + EMA_{t-1} × (1 − α)
            α = 2 / (9 + 1) = 0.2

        Operación: 1 multiplicación + 1 multiplicación + 1 suma = O(1)
        """
        if state.ema_fast is None:
            return  # Sin seed aún
        state.ema_fast = close * self._alpha_fast + state.ema_fast * (1.0 - self._alpha_fast)

    def _update_ema_slow(self, state: SymbolIndicatorState, close: float) -> None:
        """
        EMA 21 incremental:
            EMA_t = close × α + EMA_{t-1} × (1 − α)
            α = 2 / (21 + 1) ≈ 0.0909

        Operación: O(1)
        """
        if state.ema_slow is None:
            return
        state.ema_slow = close * self._alpha_slow + state.ema_slow * (1.0 - self._alpha_slow)

    def _update_rsi(self, state: SymbolIndicatorState, close: float) -> None:
        """
        RSI 14 incremental con suavizado de Wilder:

            delta = close − prev_close
            gain  = max(delta, 0)
            loss  = |min(delta, 0)|

            avg_gain_t = (avg_gain_{t-1} × (period − 1) + gain) / period
            avg_loss_t = (avg_loss_{t-1} × (period − 1) + loss) / period

            RS  = avg_gain / avg_loss
            RSI = 100 − (100 / (1 + RS))

        Nota sobre el suavizado de Wilder:
            Es equivalente a una EMA con α = 1/period.
            La fórmula clásica es:
                avg = (prev_avg × (period - 1) + current) / period
            Esto le da un 93.3% de peso al histórico y 6.67% al dato nuevo
            (para period=14), produciendo una curva más suave que EMA estándar.

        Operación: O(1) — 2 comparaciones + 4 multiplicaciones + 2 divisiones
        """
        if state.avg_gain is None or state.avg_loss is None or state.prev_close is None:
            return

        period = state.rsi_period
        delta = close - state.prev_close

        # Separar en gain y loss (mutuamente excluyentes)
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0

        # Suavizado de Wilder
        # avg_gain_t = (avg_gain_{t-1} × (period - 1) + gain_t) / period
        state.avg_gain = (state.avg_gain * (period - 1) + gain) / period
        state.avg_loss = (state.avg_loss * (period - 1) + loss) / period

        # Calcular RSI con protección de edge cases
        state.rsi = self._compute_rsi(state.avg_gain, state.avg_loss)

    # ════════════════════════════════════════════════════════════════
    #  HELPERS
    # ════════════════════════════════════════════════════════════════

    @staticmethod
    def _compute_rsi(avg_gain: float, avg_loss: float) -> float:
        """
        RSI = 100 − (100 / (1 + RS))
        RS  = avg_gain / avg_loss

        Edge cases:
        - avg_loss == 0 → RSI = 100.0 (solo ganancias, mercado totalmente alcista)
        - avg_gain == 0 → RSI = 0.0   (solo pérdidas, mercado totalmente bajista)
        - Ambos == 0    → RSI = 50.0   (sin movimiento, neutral)
        """
        if avg_gain == 0.0 and avg_loss == 0.0:
            return 50.0  # Sin movimiento → neutral
        if avg_loss == 0.0:
            return 100.0  # Solo ganancias
        if avg_gain == 0.0:
            return 0.0  # Solo pérdidas

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def get_indicators(self, symbol: str) -> Optional[dict]:
        """Obtener snapshot de indicadores para un símbolo."""
        state = self._state_manager.get(symbol)
        if state is None:
            return None
        return state.to_dict()

    def get_all_indicators(self) -> dict:
        """Snapshot de todos los indicadores para API."""
        return self._state_manager.snapshot()

