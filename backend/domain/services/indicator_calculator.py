"""
QuantPulse – Domain Service: Indicator Calculator
===================================================
Cálculos de indicadores técnicos puros.

Este servicio calcula EMA, RSI y otros indicadores
sin dependencias externas (no TA-Lib, solo math puro).

VENTAJA:
- Testeo unitario sin mocks
- Sin dependencias de librerías externas en el dominio
- Fórmulas explícitas y auditables
"""

from __future__ import annotations

from typing import List, Optional


class IndicatorCalculator:
    """
    Calculadora de indicadores técnicos puros.
    
    RESPONSABILIDAD:
    Implementar las fórmulas matemáticas de indicadores.
    NO mantiene estado (stateless).
    
    Para cálculos incrementales con estado, ver IndicatorService
    en la capa de application/infrastructure.
    """
    
    @staticmethod
    def ema(
        prices: List[float],
        period: int,
    ) -> Optional[float]:
        """
        Calcula EMA (Exponential Moving Average).
        
        FÓRMULA:
        EMA_t = price_t × k + EMA_{t-1} × (1-k)
        k = 2 / (period + 1)
        
        INICIALIZACIÓN:
        EMA inicial = SMA de los primeros `period` valores.
        
        Args:
            prices: Lista de precios (más antiguo primero)
            period: Período de la EMA
        
        Returns:
            Valor EMA actual, o None si no hay suficientes datos
        """
        if len(prices) < period:
            return None
        
        # Calcular SMA inicial
        sma = sum(prices[:period]) / period
        
        # Factor de suavizado
        k = 2.0 / (period + 1)
        
        # Calcular EMA iterativamente
        ema = sma
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        
        return ema
    
    @staticmethod
    def rsi(
        prices: List[float],
        period: int = 14,
    ) -> Optional[float]:
        """
        Calcula RSI (Relative Strength Index).
        
        FÓRMULA:
        RSI = 100 - (100 / (1 + RS))
        RS = avg_gain / avg_loss
        
        INTERPRETACIÓN:
        RSI < 30 → oversold
        RSI > 70 → overbought
        
        Args:
            prices: Lista de precios (más antiguo primero)
            period: Período del RSI (default 14)
        
        Returns:
            Valor RSI [0-100], o None si no hay suficientes datos
        """
        if len(prices) < period + 1:
            return None
        
        # Calcular cambios
        changes = [
            prices[i] - prices[i-1]
            for i in range(1, len(prices))
        ]
        
        # Separar gains y losses
        gains = [max(0, c) for c in changes]
        losses = [abs(min(0, c)) for c in changes]
        
        # Calcular promedios
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        # Protección división por cero
        if avg_loss == 0:
            return 100.0  # No hay pérdidas → RSI máximo
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi
    
    @staticmethod
    def sma(
        prices: List[float],
        period: int,
    ) -> Optional[float]:
        """
        Calcula SMA (Simple Moving Average).
        
        FÓRMULA:
        SMA = sum(prices[-period:]) / period
        
        Args:
            prices: Lista de precios
            period: Período del SMA
        
        Returns:
            Valor SMA, o None si no hay suficientes datos
        """
        if len(prices) < period:
            return None
        
        return sum(prices[-period:]) / period
    
    @staticmethod
    def atr(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14,
    ) -> Optional[float]:
        """
        Calcula ATR (Average True Range).
        
        FÓRMULA:
        TR = max(high-low, |high-prev_close|, |low-prev_close|)
        ATR = SMA(TR, period)
        
        Args:
            highs: Lista de máximos
            lows: Lista de mínimos
            closes: Lista de cierres
            period: Período del ATR
        
        Returns:
            Valor ATR, o None si no hay suficientes datos
        """
        n = len(closes)
        if n < period + 1 or len(highs) != n or len(lows) != n:
            return None
        
        # Calcular True Range para cada vela
        true_ranges = []
        for i in range(1, n):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_ranges.append(max(high_low, high_close, low_close))
        
        # ATR = SMA de los últimos `period` TR
        if len(true_ranges) < period:
            return None
        
        return sum(true_ranges[-period:]) / period
    
    @staticmethod
    def bollinger_bands(
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0,
    ) -> Optional[tuple]:
        """
        Calcula Bandas de Bollinger.
        
        FÓRMULA:
        Middle = SMA(period)
        Upper = Middle + std_dev × σ
        Lower = Middle - std_dev × σ
        
        Args:
            prices: Lista de precios
            period: Período del SMA
            std_dev: Multiplicador de desviación estándar
        
        Returns:
            Tuple (upper, middle, lower) o None
        """
        if len(prices) < period:
            return None
        
        recent = prices[-period:]
        middle = sum(recent) / period
        
        # Calcular desviación estándar
        variance = sum((p - middle) ** 2 for p in recent) / period
        sigma = variance ** 0.5
        
        upper = middle + std_dev * sigma
        lower = middle - std_dev * sigma
        
        return (upper, middle, lower)
    
    @staticmethod
    def momentum(
        prices: List[float],
        period: int = 10,
    ) -> Optional[float]:
        """
        Calcula Momentum simple.
        
        FÓRMULA:
        Momentum = (price_current / price_n_periods_ago - 1) × 100
        
        Args:
            prices: Lista de precios
            period: Períodos hacia atrás
        
        Returns:
            Momentum en %, o None si no hay suficientes datos
        """
        if len(prices) <= period:
            return None
        
        old_price = prices[-(period + 1)]
        current = prices[-1]
        
        if old_price == 0:
            return None
        
        return (current / old_price - 1) * 100
