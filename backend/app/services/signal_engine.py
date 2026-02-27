"""
QuantPulse – Signal Engine (Multi-Confirmation)
=================================================
Motor de señales profesional con confirmación múltiple.

═══════════════════════════════════════════════════════════════
           LÓGICA ESTRATÉGICA PARA SCALPING / SWING CORTO
═══════════════════════════════════════════════════════════════

HORIZONTE: Flexible — desde micro-scalps (1-5 min) hasta swings
cortos (15-30+ min). La duración NO filtra entradas.

El mercado de Deriv synthetics es 24/7 sin gaps fundamentales.
Los patrones técnicos dominan porque no hay noticias ni earnings.
Esto hace que la multi-confirmación técnica sea especialmente
efectiva en estos instrumentos.

FILOSOFÍA DE CONFIRMACIÓN MÚLTIPLE:
  Una sola condición tiene ~50-55% de acierto.
  Dos condiciones independientes elevan a ~60-65%.
  Tres condiciones pueden alcanzar ~70%+ en mercados sintéticos.

  Exigimos ≥2 condiciones coincidentes para reducir falsos positivos
  manteniendo suficiente frecuencia de señales.

PRIORIDAD DE VALIDACIÓN:
  Calidad estructural + RR válido > duración estimada.
  La duración estimada se calcula y registra como dato INFORMATIVO,
  pero NUNCA bloquea la emisión de una señal.

═══════════════════════════════════════════════════════════════
          CONDICIONES DE CONFIRMACIÓN (5 TOTAL)
═══════════════════════════════════════════════════════════════

1. CRUCE EMA (ema_cross):
   - Se detecta comparando la posición relativa de EMA9 vs EMA21
     en la vela ANTERIOR vs la vela ACTUAL (ambas cerradas).
   - Bullish: prev(EMA9 < EMA21) AND curr(EMA9 > EMA21)
   - Bearish: prev(EMA9 > EMA21) AND curr(EMA9 < EMA21)

   CÓMO SE EVITAN FALSOS POSITIVOS:
   - Se requiere CRUCE REAL (cambio de signo en la diferencia),
     no simplemente EMA9 > EMA21 (que puede mantenerse muchas velas).
   - El cruce se detecta con una sola comparación: el SIGNO de
     (ema_fast - ema_slow) cambió entre la vela anterior y actual.

2. RSI EXTREMO CON GIRO (rsi_reversal):
   - No basta que RSI esté en zona extrema (< 35 o > 65).
   - TAMBIÉN debe estar GIRANDO: RSI actual vs RSI anterior.
   - BUY:  RSI < 35 AND RSI > prev_RSI (sobreventa + recuperando)
   - SELL: RSI > 65 AND RSI < prev_RSI (sobrecompra + cayendo)

   CÓMO SE EVITAN FALSOS POSITIVOS:
   - RSI en zona extrema SIN giro = mercado cayendo fuerte → no
     contratendencia. El giro confirma que la presión se agota.

3. REBOTE EN S/R (sr_bounce):
   - BUY:  precio toca soporte dinámico + vela alcista = rebote.
   - SELL: precio toca resistencia dinámica + vela bajista = rechazo.
   - Ver SupportResistanceService para detalle de detección.

4. RUPTURA (breakout):
   - BUY:  close > resistencia + vela fuerte (rango > promedio × mult).
   - SELL: close < soporte + vela fuerte.
   - CÓMO SE CONFIRMA con tamaño de vela:
     Una ruptura con vela pequeña es probablemente falsa.
     Exigir rango > 1.2× promedio filtra rupturas débiles.

5. FILTRO DE CONSOLIDACIÓN (filtro negativo, NO es "condición"):
   - Si el mercado está consolidando → NO generar señal.
   - Se aplica ANTES de evaluar condiciones → eficiente.

═══════════════════════════════════════════════════════════════
         GESTIÓN DE RIESGO AUTOMÁTICA
═══════════════════════════════════════════════════════════════

ENTRY:
  Precio de cierre de la vela confirmada.
  → No el high/low → evita slippage en la simulación.

STOP LOSS (técnico):
  BUY  → debajo del último swing low detectado.
  SELL → encima del último swing high detectado.

  CÓMO SE VALIDA SL MATEMÁTICAMENTE:
  sl_distance = |entry - stop_loss|
  sl_pct      = sl_distance / entry
  Si sl_pct < min_sl_pct → SL demasiado cerca → señal inválida.
  Esto evita SL por ruido que sería ejecutado inmediatamente.

  NOTA: Un SL corto con RR válido ≥1:1 es ACEPTABLE.
  No se rechaza la señal por SL cercano si el RR es válido.

TAKE PROFIT (basado en RR):
  BUY:  TP = entry + (sl_distance × rr_ratio)
  SELL: TP = entry - (sl_distance × rr_ratio)

  VALIDACIÓN RR:
  actual_rr = tp_distance / sl_distance
  Si actual_rr < min_rr (configurable, default=1.0) → señal rechazada.

DURACIÓN ESTIMADA (INFORMATIVA):
  Se calcula basándose en la volatilidad reciente y la distancia al TP.
  Se incluye en la señal como dato adicional para el trader.
  NO se usa como filtro de entrada. NUNCA bloquea una señal.

═══════════════════════════════════════════════════════════════
         ANTI-REPAINTING Y ANTI-DUPLICADOS
═══════════════════════════════════════════════════════════════

ANTI-REPAINTING:
  - evaluate() SOLO se llama con velas CERRADAS (inmutables).
  - Los indicadores se calcularon con datos finales de vela.
  - Los niveles S/R se detectaron con velas ya cerradas.
  → Una señal emitida NUNCA desaparece ni cambia.

ANTI-DUPLICADOS:
  - Se almacena el timestamp de la última señal por símbolo.
  - Cooldown configurable (N×intervalo segundos entre señales).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, Optional, Any

from backend.app.core.logging import get_logger
from backend.app.domain.entities.candle import Candle
from backend.app.domain.entities.signal import Signal
from backend.app.services.support_resistance_service import SupportResistanceService

# Importación condicional de ML (opcional)
try:
    from backend.ml.model_inference import ModelInference
    HAS_ML = True
except ImportError:
    HAS_ML = False
    ModelInference = None

logger = get_logger("signal_engine")


# ─── Nombres de condiciones (para log y auditoría) ─────────────────
COND_EMA_CROSS = "ema_cross"
COND_EMA_TREND = "ema_trend"
COND_RSI_REVERSAL = "rsi_reversal"
COND_SR_BOUNCE = "sr_bounce"
COND_BREAKOUT = "breakout"


class SignalEngine:
    """
    Motor de señales multi-confirmación para scalping.

    Recibe: vela cerrada + indicadores + buffer de velas.
    Genera: Signal (BUY/SELL) si hay ≥ min_confirmations.
    NO ejecuta trades. NO persiste. Solo emite señales.

    Complejidad: O(1) por evaluación (O(K=10) para filtro consolidación).

    PREPARADO PARA CONECTAR CON TRADE SIMULATOR (Fase 4):
    Signal.to_dict() → SimulatedTrade → estadísticas de rendimiento.
    """

    def __init__(
        self,
        sr_service: SupportResistanceService,
        *,
        min_confirmations: int = 2,
        rr_ratio: float = 2.0,
        min_rr: float = 1.5,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        min_sl_pct: float = 0.0002,
        cooldown_candles: int = 3,
        candle_interval: int = 5,
        ml_inference: Optional[Any] = None,  # ModelInference when ML available
        ml_threshold: float = 0.55,
        ml_enabled: bool = False,
    ) -> None:
        self._sr_service = sr_service
        self._min_confirmations = min_confirmations
        self._rr_ratio = rr_ratio
        self._min_rr = min_rr
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._min_sl_pct = min_sl_pct
        self._candle_interval = candle_interval
        self._cooldown_candles = cooldown_candles
        self._cooldown_seconds = cooldown_candles * candle_interval
        
        # ML Integration (opcional)
        self._ml_inference = ml_inference
        self._ml_threshold = ml_threshold
        self._ml_enabled = ml_enabled and HAS_ML and ml_inference is not None
        self._ml_filtered = 0  # Señales filtradas por ML

        # ── Estado interno por símbolo ─────────────────────────────
        # Indicadores de la vela ANTERIOR para detectar cruces/giros.
        self._prev_indicators: Dict[str, dict] = {}
        # Timestamp de la última señal emitida por símbolo.
        self._last_signal_ts: Dict[str, float] = {}
        # Buffer de señales recientes por símbolo (para API).
        self._recent_signals: Dict[str, deque] = {}

        # Contadores de diagnóstico
        self._total_evaluated = 0
        self._total_signals = 0
        self._total_filtered_consolidation = 0
        self._total_filtered_rr = 0
        self._signals_by_type: Dict[str, int] = {"BUY": 0, "SELL": 0}

        logger.info(
            "SignalEngine inicializado "
            "(min_confirm=%d, RR=%.1f, min_RR=%.1f, "
            "RSI_OS=%.0f, RSI_OB=%.0f, min_SL=%.4f%%, cooldown=%ds)",
            min_confirmations, rr_ratio, min_rr,
            rsi_oversold, rsi_overbought, min_sl_pct * 100,
            self._cooldown_seconds,
        )

    # ════════════════════════════════════════════════════════════════
    #  PUNTO DE ENTRADA PRINCIPAL
    # ════════════════════════════════════════════════════════════════

    def evaluate(
        self,
        candle: Candle,
        indicators: dict,
        candles_buffer: deque,
    ) -> Optional[Signal]:
        """
        Evaluar si la vela cerrada + indicadores generan una señal válida.

        FLUJO:
          1. Validar pre-condiciones (warm-up, datos previos)
          2. Anti-duplicados (cooldown entre señales)
          3. Filtro de consolidación → mercado lateral → skip
          4. Evaluar 4 condiciones para BUY y SELL
          5. Contar confirmaciones
          6. Si ≥ min_confirmations → calcular riesgo → validar RR
          7. Generar Signal o None

        ANTI-REPAINTING:
          Esta función SOLO se llama con velas CERRADAS e indicadores
          calculados sobre datos finales. Nunca con datos en construcción.

        Complejidad: O(1) amortizado (O(10) para filtro consolidación).

        Args:
            candle: Vela recién cerrada (inmutable, frozen=True).
            indicators: Dict con ema_9, ema_21, rsi_14 actuales.
            candles_buffer: Buffer de velas del símbolo (deque).

        Returns:
            Signal si se genera señal válida, None si no.
        """
        self._total_evaluated += 1
        symbol = candle.symbol

        # ── 1. Validar pre-condiciones ──────────────────────────────
        # Sin indicadores no podemos evaluar ninguna condición.
        ema_9 = indicators.get("ema_9")
        ema_21 = indicators.get("ema_21")
        rsi = indicators.get("rsi_14")

        if ema_9 is None or ema_21 is None or rsi is None:
            # Indicadores aún en warm-up → almacenar y esperar
            self._prev_indicators[symbol] = indicators
            return None

        prev = self._prev_indicators.get(symbol)
        if prev is None or prev.get("ema_9") is None:
            # Primera evaluación con indicadores listos → necesitamos
            # al menos 2 lecturas para detectar cruces/giros.
            self._prev_indicators[symbol] = indicators
            return None

        # ── 2. Anti-duplicados: cooldown (dinámico según intervalo de vela)
        cooldown = self._cooldown_candles * candle.interval
        last_ts = self._last_signal_ts.get(symbol, 0.0)
        if candle.timestamp - last_ts < cooldown:
            self._prev_indicators[symbol] = indicators
            return None

        # ── 3. Filtro de consolidación ──────────────────────────────
        # Si el mercado está en rango estrecho → no operar.
        if self._sr_service.is_consolidating(candles_buffer):
            self._total_filtered_consolidation += 1
            self._prev_indicators[symbol] = indicators
            return None

        # ── 4. Evaluar las 4 condiciones ────────────────────────────
        buy_conditions: list[str] = []
        sell_conditions: list[str] = []

        self._check_ema_cross(
            ema_9, ema_21, prev, buy_conditions, sell_conditions,
        )
        self._check_ema_trend(
            ema_9, ema_21, buy_conditions, sell_conditions,
        )
        self._check_rsi_reversal(
            rsi, prev, buy_conditions, sell_conditions,
        )

        # S/R: obtener niveles para rebote/ruptura
        price = candle.close
        support = self._sr_service.get_nearest_support(symbol, price)
        resistance = self._sr_service.get_nearest_resistance(symbol, price)
        avg_range = self._sr_service.compute_avg_range(candles_buffer)

        self._check_sr_bounce(
            candle, support, resistance, buy_conditions, sell_conditions,
        )
        self._check_breakout(
            candle, support, resistance, avg_range,
            buy_conditions, sell_conditions,
        )

        # ── 5. Actualizar estado previo (ANTES de return) ──────────
        self._prev_indicators[symbol] = indicators

        # ── DEBUG: mostrar evaluación de condiciones cada N velas ──
        total_conds = len(buy_conditions) + len(sell_conditions)
        if total_conds > 0 or self._total_evaluated % 50 == 0:
            logger.info(
                "🔍 [%s] eval #%d | BUY=%s SELL=%s | "
                "EMA9=%.5f EMA21=%.5f RSI=%.2f | S=%.5f R=%.5f",
                symbol, self._total_evaluated,
                buy_conditions or "[]", sell_conditions or "[]",
                ema_9, ema_21, rsi,
                support or 0.0, resistance or 0.0,
            )

        # ── 6. Determinar dirección con suficientes confirmaciones ──
        signal_type: Optional[str] = None
        conditions: list[str] = []

        if len(buy_conditions) >= self._min_confirmations:
            signal_type = "BUY"
            conditions = buy_conditions
        elif len(sell_conditions) >= self._min_confirmations:
            signal_type = "SELL"
            conditions = sell_conditions
        else:
            # Sin suficientes confirmaciones → NEUTRAL → sin señal
            if total_conds > 0:
                logger.info(
                    "⏸️  [%s] %d condicion(es) insuficientes (min=%d) "
                    "BUY=%s SELL=%s",
                    symbol, total_conds, self._min_confirmations,
                    buy_conditions, sell_conditions,
                )
            return None

        # ── 7. Gestión de riesgo → Signal o None ───────────────────
        signal = self._compute_risk_and_generate(
            candle, signal_type, conditions, symbol, avg_range,
        )

        # ── 8. Filtro ML (opcional) ────────────────────────────────
        if signal is not None and self._ml_enabled:
            signal = self._apply_ml_filter(
                signal, candle, indicators, symbol,
            )

        if signal is not None:
            self._last_signal_ts[symbol] = candle.timestamp
            self._total_signals += 1
            self._signals_by_type[signal_type] += 1
            self._store_recent_signal(signal)

            logger.info(
                "⚡ SEÑAL %s [%s] entry=%.5f SL=%.5f TP=%.5f RR=%.2f "
                "condiciones=%s confianza=%d est_dur=%.1fmin",
                signal.signal_type, signal.symbol,
                signal.entry, signal.stop_loss, signal.take_profit,
                signal.rr, list(signal.conditions), signal.confidence,
                signal.estimated_duration,
            )

        return signal

    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 1: CRUCE EMA
    # ════════════════════════════════════════════════════════════════

    def _check_ema_cross(
        self,
        ema_9: float,
        ema_21: float,
        prev: dict,
        buy_conds: list[str],
        sell_conds: list[str],
    ) -> None:
        """
        Detectar cruce real de EMA 9 vs EMA 21.

        CÓMO SE DETECTA CRUCE REAL SIN FALSOS POSITIVOS:

        Se compara el SIGNO de la diferencia (ema9 - ema21) entre
        la vela anterior y la actual:

          prev_diff = prev_ema9 - prev_ema21
          curr_diff = curr_ema9 - curr_ema21

          Cruce alcista: prev_diff < 0 AND curr_diff > 0
            → EMA9 estaba DEBAJO y ahora está ARRIBA.

          Cruce bajista: prev_diff > 0 AND curr_diff < 0
            → EMA9 estaba ARRIBA y ahora está DEBAJO.

        Si ambos tienen el MISMO signo → no hay cruce.
        Si alguno es exactamente 0 → EMAs iguales, no cruce definitivo.

        Este método detecta EXACTAMENTE EL CANDLE del cruce,
        no las velas posteriores donde EMA9 sigue arriba/abajo.
        """
        prev_ema_9 = prev.get("ema_9")
        prev_ema_21 = prev.get("ema_21")

        if prev_ema_9 is None or prev_ema_21 is None:
            return

        prev_diff = prev_ema_9 - prev_ema_21
        curr_diff = ema_9 - ema_21

        # Cruce alcista: de negativo a positivo
        if prev_diff < 0 and curr_diff > 0:
            buy_conds.append(COND_EMA_CROSS)

        # Cruce bajista: de positivo a negativo
        elif prev_diff > 0 and curr_diff < 0:
            sell_conds.append(COND_EMA_CROSS)

    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 1b: EMA TREND ALIGNMENT (más suave que cruce)
    # ════════════════════════════════════════════════════════════════
    def _check_ema_trend(self, ema_9, ema_21, buy_conds, sell_conds):
        """
        Alineación de tendencia EMA — condición más suave que el cruce.
        Se activa cuando EMA9 está alineada con la dirección de tendencia:
          - BUY:  EMA9 > EMA21 (alineación alcista)
          - SELL: EMA9 < EMA21 (alineación bajista)
        """
        if ema_9 > ema_21:
            buy_conds.append(COND_EMA_TREND)
        elif ema_9 < ema_21:
            sell_conds.append(COND_EMA_TREND)

    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 2: RSI CON GIRO
    # ════════════════════════════════════════════════════════════════

    def _check_rsi_reversal(
        self,
        rsi: float,
        prev: dict,
        buy_conds: list[str],
        sell_conds: list[str],
    ) -> None:
        """
        Detectar RSI en zona extrema CON giro confirmado.

        CÓMO SE EVITA RSI EXTREMO SIN CONFIRMACIÓN:

        Un RSI de 30 que SIGUE CAYENDO indica momentum bajista fuerte
        → comprar sería contratendencia peligrosa.

        Solo señalamos BUY si RSI < 35 Y RSI_actual > RSI_anterior
        (el RSI está girando al alza desde la sobreventa).

        Análogamente, solo SELL si RSI > 65 Y RSI_actual < RSI_anterior
        (girando a la baja desde la sobrecompra).
        """
        prev_rsi = prev.get("rsi_14")
        if prev_rsi is None:
            return

        # BUY: sobreventa + girando al alza
        if rsi < self._rsi_oversold and rsi > prev_rsi:
            buy_conds.append(COND_RSI_REVERSAL)

        # SELL: sobrecompra + girando a la baja
        if rsi > self._rsi_overbought and rsi < prev_rsi:
            sell_conds.append(COND_RSI_REVERSAL)

    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 3: REBOTE EN S/R
    # ════════════════════════════════════════════════════════════════

    def _check_sr_bounce(
        self,
        candle: Candle,
        support: Optional[float],
        resistance: Optional[float],
        buy_conds: list[str],
        sell_conds: list[str],
    ) -> None:
        """
        Detectar rebote en soporte (BUY) o rechazo en resistencia (SELL).

        CÓMO SE DETECTA REBOTE EN SOPORTE:
        1. Swing low detectado previamente define nivel de soporte.
        2. La vela actual tiene un low cercano al soporte (tolerancia %).
        3. El close está por encima del soporte (el soporte "sostuvo").
        4. La vela es alcista (close > open).

        CÓMO SE DETECTA RECHAZO EN RESISTENCIA:
        1. Swing high detectado previamente define nivel de resistencia.
        2. La vela actual tiene un high cercano a la resistencia.
        3. El close está por debajo de la resistencia (la resistencia "aguantó").
        4. La vela es bajista (close < open).
        """
        if self._sr_service.is_bounce_on_support(candle, support):
            buy_conds.append(COND_SR_BOUNCE)

        if self._sr_service.is_rejection_at_resistance(candle, resistance):
            sell_conds.append(COND_SR_BOUNCE)

    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 4: RUPTURA
    # ════════════════════════════════════════════════════════════════

    def _check_breakout(
        self,
        candle: Candle,
        support: Optional[float],
        resistance: Optional[float],
        avg_range: float,
        buy_conds: list[str],
        sell_conds: list[str],
    ) -> None:
        """
        Detectar ruptura de S/R con confirmación de fuerza (tamaño de vela).

        CÓMO SE CONFIRMA CON TAMAÑO DE VELA > PROMEDIO:

          avg_range = promedio(high - low) de las últimas N velas.
          candle_range = high - low de la vela actual.

          Si candle_range > avg_range × breakout_multiplier → vela fuerte.

        JUSTIFICACIÓN:
        Una "ruptura" con una vela diminuta es probable fake breakout.
        Exigir que la vela sea significativamente más grande que el
        promedio asegura momentum real detrás de la ruptura.
        El multiplicador de 1.2x es conservador para scalping;
        se puede ajustar según el instrumento.
        """
        if self._sr_service.is_breakout_above(candle, resistance, avg_range):
            buy_conds.append(COND_BREAKOUT)

        if self._sr_service.is_breakout_below(candle, support, avg_range):
            sell_conds.append(COND_BREAKOUT)

    # ════════════════════════════════════════════════════════════════
    #  GESTIÓN DE RIESGO
    # ════════════════════════════════════════════════════════════════

    def _compute_risk_and_generate(
        self,
        candle: Candle,
        signal_type: str,
        conditions: list[str],
        symbol: str,
        avg_range: float = 0.0,
    ) -> Optional[Signal]:
        """
        Calcular Entry, Stop Loss, Take Profit y validar RR.

        CÓMO SE VALIDA RR MATEMÁTICAMENTE:

        1. Entry = close de la vela confirmada (dato final, no provisional).

        2. Stop Loss:
           BUY  → SL = soporte más cercano debajo del entry (swing low)
           SELL → SL = resistencia más cercana encima del entry (swing high)

           Si no hay swing → no se puede calcular SL → señal descartada.

        3. SL Distance:
           sl_distance = |entry - stop_loss|
           sl_pct = sl_distance / entry

           Si sl_pct < min_sl_pct → SL demasiado cercano → probablemente
           sería ejecutado por ruido → señal inválida.

        4. Take Profit:
           tp_distance = sl_distance × rr_ratio
           BUY:  TP = entry + tp_distance
           SELL: TP = entry - tp_distance

        5. RR Validación:
           actual_rr = tp_distance / sl_distance
           Si actual_rr < min_rr → descartada.

        JUSTIFICACIÓN MATEMÁTICA:
        Con RR = 1:1, necesitamos acertar el 50% para breakeven.
        Con RR = 2:1, necesitamos acertar solo el 34% para breakeven:
          WinRate_min = 1 / (1 + RR) = 1 / (1 + 2) = 33.3%
        Con 2+ confirmaciones apuntamos a WinRate > 50%, lo cual
        con cualquier RR ≥ 1:1 genera rentabilidad consistente.

        DURACIÓN ESTIMADA (INFORMATIVA):
        Se calcula basándose en la volatilidad reciente (ATR) y la
        distancia al TP. Se incluye en la señal pero NUNCA la bloquea.
        Permite al trader saber si es micro-scalp o swing corto.
        """
        entry = candle.close

        # ── Obtener SL desde swing points ────────────────────────
        if signal_type == "BUY":
            sl_level = self._sr_service.get_nearest_support(symbol, entry)
            if sl_level is None:
                sl_level = self._sr_service.get_last_swing_low(symbol)
            if sl_level is None or sl_level >= entry:
                # Sin soporte válido debajo del entry → sin SL → sin señal
                logger.debug(
                    "Señal %s [%s] descartada: sin swing low válido para SL",
                    signal_type, symbol,
                )
                return None

            stop_loss = sl_level
            sl_distance = entry - stop_loss
            tp_distance = sl_distance * self._rr_ratio
            take_profit = entry + tp_distance

        else:  # SELL
            sl_level = self._sr_service.get_nearest_resistance(symbol, entry)
            if sl_level is None:
                sl_level = self._sr_service.get_last_swing_high(symbol)
            if sl_level is None or sl_level <= entry:
                logger.debug(
                    "Señal %s [%s] descartada: sin swing high válido para SL",
                    signal_type, symbol,
                )
                return None

            stop_loss = sl_level
            sl_distance = stop_loss - entry
            tp_distance = sl_distance * self._rr_ratio
            take_profit = entry - tp_distance

        # ── Validar distancia SL mínima ──────────────────────────
        sl_pct = sl_distance / entry if entry != 0 else 0
        if sl_pct < self._min_sl_pct:
            logger.debug(
                "Señal %s [%s] descartada: SL=%.6f%% < mínimo %.4f%%",
                signal_type, symbol, sl_pct * 100, self._min_sl_pct * 100,
            )
            self._total_filtered_rr += 1
            return None

        # ── Validar RR ───────────────────────────────────────────
        actual_rr = tp_distance / sl_distance if sl_distance > 0 else 0
        if actual_rr < self._min_rr:
            logger.debug(
                "Señal %s [%s] descartada: RR=%.2f < mínimo %.2f",
                signal_type, symbol, actual_rr, self._min_rr,
            )
            self._total_filtered_rr += 1
            return None

        # ── Duración estimada (INFORMATIVA, nunca filtra) ────────
        if avg_range > 0:
            candles_to_tp = tp_distance / avg_range
            est_dur = (candles_to_tp * candle.interval) / 60.0
        else:
            est_dur = 0.0

        # ── Generar señal inmutable ──────────────────────────────
        return Signal(
            id=Signal.generate_id(),
            symbol=symbol,
            signal_type=signal_type,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            rr=actual_rr,
            timestamp=time.time(),
            candle_timestamp=candle.timestamp,
            conditions=tuple(conditions),
            confidence=len(conditions),
            estimated_duration=round(est_dur, 1),
        )

    # ════════════════════════════════════════════════════════════════
    #  ALMACENAMIENTO DE SEÑALES RECIENTES (para API)
    # ════════════════════════════════════════════════════════════════

    def _store_recent_signal(self, signal: Signal) -> None:
        """Almacenar señal en buffer reciente para API de consulta."""
        symbol = signal.symbol
        if symbol not in self._recent_signals:
            self._recent_signals[symbol] = deque(maxlen=50)
        self._recent_signals[symbol].append(signal)

    def get_recent_signals(
        self, symbol: str | None = None, count: int = 20,
    ) -> list[dict]:
        """
        Obtener señales recientes para API.
        Si symbol=None, retorna de todos los símbolos mezcladas.
        """
        if symbol is not None:
            buffer = self._recent_signals.get(symbol, deque())
            signals = list(buffer)[-count:]
            return [s.to_dict() for s in signals]

        # Todas las señales, ordenadas por timestamp
        all_signals: list[Signal] = []
        for buf in self._recent_signals.values():
            all_signals.extend(buf)
        all_signals.sort(key=lambda s: s.timestamp, reverse=True)
        return [s.to_dict() for s in all_signals[:count]]

    # ════════════════════════════════════════════════════════════════
    #  DIAGNÓSTICO / API
    # ════════════════════════════════════════════════════════════════

    @property
    def stats(self) -> dict:
        """Estadísticas del motor de señales para monitoring."""
        base_stats = {
            "total_evaluated": self._total_evaluated,
            "total_signals": self._total_signals,
            "signals_buy": self._signals_by_type.get("BUY", 0),
            "signals_sell": self._signals_by_type.get("SELL", 0),
            "filtered_consolidation": self._total_filtered_consolidation,
            "filtered_rr": self._total_filtered_rr,
            "filtered_ml": self._ml_filtered,
            "signal_rate": (
                f"{self._total_signals}/{self._total_evaluated}"
                if self._total_evaluated > 0 else "N/A"
            ),
        }
        
        # Agregar estadísticas ML si está habilitado
        if self._ml_enabled and self._ml_inference is not None:
            ml_stats = self._ml_inference.get_stats()
            base_stats["ml_stats"] = ml_stats
        
        return base_stats

    # ════════════════════════════════════════════════════════════════
    #  INTEGRACIÓN ML
    # ════════════════════════════════════════════════════════════════

    def _apply_ml_filter(
        self,
        signal: Signal,
        candle: Candle,
        indicators: dict,
        symbol: str,
    ) -> Optional[Signal]:
        """
        Filtra señal usando modelo ML.
        
        FLUJO:
          1. Extraer features del contexto actual
          2. Predecir probabilidad de éxito
          3. Si P >= threshold → emitir señal
          4. Si P < threshold → descartar silenciosamente
        
        CÓMO ESTO MEJORA EL EDGE:
          El modelo aprendió qué combinaciones de features
          generan mayor probabilidad de PROFIT histórico.
          Filtramos señales con baja P para mejorar win rate
          sin afectar las señales de alta calidad.
        """
        if self._ml_inference is None:
            return signal
        
        try:
            # Construir contexto S/R para features
            price = candle.close
            sr_context = {
                "nearest_support": self._sr_service.get_nearest_support(symbol, price) or price,
                "nearest_resistance": self._sr_service.get_nearest_resistance(symbol, price) or price,
                "consolidation_bars": 0,  # TODO: extraer de sr_service
            }
            
            # Extraer features
            features = self._ml_inference.extract_features(
                candle=candle,
                indicators=indicators,
                sr_context=sr_context,
                signal_type=signal.signal_type,
                planned_rr=signal.rr,
            )
            
            # Predecir
            result = self._ml_inference.predict(
                features=features,
                threshold=self._ml_threshold,
            )
            
            if result.should_emit:
                # Señal pasa el filtro ML
                logger.debug(
                    "ML: Señal %s [%s] APROBADA (P=%.2f%% >= %.0f%%)",
                    signal.signal_type, symbol,
                    result.probability * 100, self._ml_threshold * 100,
                )
                # Agregar metadata ML a la señal
                signal = self._enrich_signal_with_ml(signal, result)
                return signal
            else:
                # Señal filtrada por ML
                self._ml_filtered += 1
                logger.info(
                    "ML: Señal %s [%s] FILTRADA (P=%.2f%% < %.0f%%)",
                    signal.signal_type, symbol,
                    result.probability * 100, self._ml_threshold * 100,
                )
                return None
                
        except Exception as e:
            # En caso de error ML → emitir señal (fail-safe)
            logger.warning("Error en filtro ML: %s. Emitiendo señal.", e)
            return signal
    
    def _enrich_signal_with_ml(
        self,
        signal: Signal,
        ml_result,
    ) -> Signal:
        """
        Enriquece la señal con metadata ML.
        
        NOTA: Signal es inmutable (frozen dataclass), se crea una nueva
        con el campo ml_probability poblado.
        """
        # Crear nueva señal con probabilidad ML
        return Signal(
            id=signal.id,
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            rr=signal.rr,
            timestamp=signal.timestamp,
            candle_timestamp=signal.candle_timestamp,
            conditions=signal.conditions,
            confidence=signal.confidence,
            estimated_duration=signal.estimated_duration,
            ml_probability=ml_result.probability,
        )
    
    def enable_ml(
        self,
        inference: Any,  # ModelInference instance
        threshold: float = None,
    ):
        """Habilita filtrado ML en runtime."""
        self._ml_inference = inference
        if threshold is not None:
            self._ml_threshold = threshold
        self._ml_enabled = HAS_ML and inference is not None
        
        if self._ml_enabled:
            logger.info(
                "ML habilitado: threshold=%.2f%%, version=%s",
                self._ml_threshold * 100,
                inference.model_version if inference else "none",
            )
    
    def disable_ml(self):
        """Deshabilita filtrado ML."""
        self._ml_enabled = False
        logger.info("ML deshabilitado")
    
    def set_ml_threshold(self, threshold: float):
        """Ajusta threshold ML en runtime."""
        self._ml_threshold = max(0.40, min(threshold, 0.80))
        logger.info("ML threshold: %.2f%%", self._ml_threshold * 100)
