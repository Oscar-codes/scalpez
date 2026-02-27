"""
QuantPulse – Domain Service: Signal Rules
===========================================
Lógica pura de evaluación de condiciones de señales.

Este servicio contiene SOLO lógica de negocio sin dependencias
externas. Puede testearse unitariamente sin mocks.

REGLAS DE CONFIRMACIÓN:
1. EMA Cross (cruce de medias)
2. RSI Reversal (RSI extremo + giro)
3. S/R Bounce (rebote en soporte/resistencia)
4. Breakout (ruptura con volumen)
5. Consolidation Filter (filtro negativo)

NOTA: Este servicio recibe DATOS ya calculados.
Los indicadores se calculan en otra capa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class SignalRulesConfig:
    """Configuración para reglas de señales."""
    
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    min_confirmations: int = 2
    ema_cross_threshold: float = 0.0001  # umbral mínimo de cruce


class SignalRules:
    """
    Servicio de dominio para evaluar condiciones de señales.
    
    RESPONSABILIDAD ÚNICA:
    Evaluar si las condiciones técnicas se cumplen.
    NO decide si emitir señal (eso es del use case).
    
    TESTABILIDAD:
    No tiene dependencias externas. Solo lógica pura.
    
    USO:
        rules = SignalRules(config)
        conditions = rules.evaluate_all(
            signal_type="BUY",
            ema_data=ema_data,
            rsi_data=rsi_data,
            sr_data=sr_data,
            candle_data=candle_data,
        )
    """
    
    def __init__(self, config: SignalRulesConfig = None):
        self._config = config or SignalRulesConfig()
    
    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 1: EMA CROSS
    # ════════════════════════════════════════════════════════════════
    
    def check_ema_cross(
        self,
        prev_ema_fast: float,
        prev_ema_slow: float,
        curr_ema_fast: float,
        curr_ema_slow: float,
    ) -> Optional[str]:
        """
        Detecta cruce de EMAs entre vela anterior y actual.
        
        LÓGICA:
        - Bullish: prev(fast < slow) AND curr(fast > slow)
        - Bearish: prev(fast > slow) AND curr(fast < slow)
        
        Args:
            prev_ema_fast: EMA rápida (9) de vela anterior
            prev_ema_slow: EMA lenta (21) de vela anterior
            curr_ema_fast: EMA rápida (9) de vela actual
            curr_ema_slow: EMA lenta (21) de vela actual
        
        Returns:
            "BUY" si cruce alcista, "SELL" si bajista, None si no hay cruce
        """
        prev_diff = prev_ema_fast - prev_ema_slow
        curr_diff = curr_ema_fast - curr_ema_slow
        
        threshold = self._config.ema_cross_threshold
        
        # Cruce alcista: diff cambió de negativo a positivo
        if prev_diff < -threshold and curr_diff > threshold:
            return "BUY"
        
        # Cruce bajista: diff cambió de positivo a negativo
        if prev_diff > threshold and curr_diff < -threshold:
            return "SELL"
        
        return None
    
    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 2: RSI REVERSAL
    # ════════════════════════════════════════════════════════════════
    
    def check_rsi_reversal(
        self,
        prev_rsi: float,
        curr_rsi: float,
    ) -> Optional[str]:
        """
        Detecta RSI en extremo CON giro de dirección.
        
        LÓGICA:
        - BUY:  RSI < oversold AND RSI > prev_RSI (sobreventa + recuperando)
        - SELL: RSI > overbought AND RSI < prev_RSI (sobrecompra + cayendo)
        
        CÓMO SE EVITAN FALSOS POSITIVOS:
        RSI en zona extrema SIN giro = mercado cayendo fuerte.
        El giro confirma que la presión se agota.
        
        Args:
            prev_rsi: RSI de vela anterior
            curr_rsi: RSI de vela actual
        
        Returns:
            "BUY" si reversal alcista, "SELL" si bajista, None si no
        """
        oversold = self._config.rsi_oversold
        overbought = self._config.rsi_overbought
        
        # Sobreventa + girando hacia arriba
        if curr_rsi < oversold and curr_rsi > prev_rsi:
            return "BUY"
        
        # Sobrecompra + girando hacia abajo
        if curr_rsi > overbought and curr_rsi < prev_rsi:
            return "SELL"
        
        return None
    
    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 3: S/R BOUNCE
    # ════════════════════════════════════════════════════════════════
    
    def check_sr_bounce(
        self,
        close: float,
        low: float,
        high: float,
        support: float,
        resistance: float,
        tolerance_pct: float = 0.002,
    ) -> Optional[str]:
        """
        Detecta rebote en soporte o resistencia.
        
        LÓGICA:
        - BUY:  low tocó soporte + cerró por encima (rebote)
        - SELL: high tocó resistencia + cerró por debajo (rechazo)
        
        Args:
            close: Precio de cierre
            low: Mínimo de la vela
            high: Máximo de la vela
            support: Nivel de soporte más cercano
            resistance: Nivel de resistencia más cercana
            tolerance_pct: Tolerancia como porcentaje del precio
        
        Returns:
            "BUY" si rebote en soporte, "SELL" si rechazo en resistencia
        """
        if support <= 0 or resistance <= 0:
            return None
        
        tolerance = close * tolerance_pct
        
        # Rebote en soporte
        if abs(low - support) <= tolerance and close > support:
            return "BUY"
        
        # Rechazo en resistencia
        if abs(high - resistance) <= tolerance and close < resistance:
            return "SELL"
        
        return None
    
    # ════════════════════════════════════════════════════════════════
    #  CONDICIÓN 4: BREAKOUT
    # ════════════════════════════════════════════════════════════════
    
    def check_breakout(
        self,
        close: float,
        candle_range: float,
        avg_range: float,
        support: float,
        resistance: float,
        breakout_mult: float = 1.2,
    ) -> Optional[str]:
        """
        Detecta ruptura de S/R con vela fuerte.
        
        LÓGICA:
        - BUY:  close > resistance + vela grande (rango > avg × mult)
        - SELL: close < support + vela grande
        
        CÓMO SE CONFIRMA:
        Una ruptura con vela pequeña es probablemente falsa.
        Exigir rango > 1.2× promedio filtra rupturas débiles.
        
        Args:
            close: Precio de cierre
            candle_range: Rango de la vela actual (high - low)
            avg_range: Rango promedio de las últimas N velas
            support: Nivel de soporte
            resistance: Nivel de resistencia
            breakout_mult: Multiplicador para considerar vela "fuerte"
        
        Returns:
            "BUY" si breakout alcista, "SELL" si bajista
        """
        if avg_range <= 0 or support <= 0 or resistance <= 0:
            return None
        
        is_strong_candle = candle_range > (avg_range * breakout_mult)
        
        if not is_strong_candle:
            return None
        
        # Breakout alcista
        if close > resistance:
            return "BUY"
        
        # Breakout bajista
        if close < support:
            return "SELL"
        
        return None
    
    # ════════════════════════════════════════════════════════════════
    #  FILTRO: CONSOLIDACIÓN
    # ════════════════════════════════════════════════════════════════
    
    def is_consolidating(
        self,
        recent_ranges: List[float],
        avg_range: float,
        atr_mult: float = 0.5,
        min_candles: int = 3,
    ) -> bool:
        """
        Detecta si el mercado está en consolidación.
        
        LÓGICA:
        Si las últimas N velas tienen rangos muy pequeños respecto
        al promedio, el mercado está "dormido" → no operar.
        
        Args:
            recent_ranges: Lista de rangos de las últimas velas
            avg_range: Rango promedio histórico
            atr_mult: Multiplicador de ATR para umbral
            min_candles: Mínimo de velas para considerar consolidación
        
        Returns:
            True si está consolidando, False si no
        """
        if len(recent_ranges) < min_candles or avg_range <= 0:
            return False
        
        threshold = avg_range * atr_mult
        small_candles = sum(1 for r in recent_ranges[:min_candles] if r < threshold)
        
        return small_candles >= min_candles
    
    # ════════════════════════════════════════════════════════════════
    #  EVALUACIÓN COMPLETA
    # ════════════════════════════════════════════════════════════════
    
    def count_confirmations(
        self,
        signal_type: str,
        conditions: List[Optional[str]],
    ) -> Tuple[List[str], int]:
        """
        Cuenta condiciones que confirman el tipo de señal.
        
        Args:
            signal_type: "BUY" o "SELL" esperado
            conditions: Lista de resultados de check_* methods
        
        Returns:
            Tupla (lista_condiciones_activas, conteo)
        """
        active = [c for c in conditions if c == signal_type]
        condition_names = []
        
        # Mapear índices a nombres de condición
        condition_map = ["ema_cross", "rsi_reversal", "sr_bounce", "breakout"]
        for i, cond in enumerate(conditions):
            if cond == signal_type and i < len(condition_map):
                condition_names.append(condition_map[i])
        
        return condition_names, len(active)
    
    def meets_minimum_confirmations(
        self,
        confirmations: int,
    ) -> bool:
        """Verifica si se alcanza el mínimo de confirmaciones."""
        return confirmations >= self._config.min_confirmations
