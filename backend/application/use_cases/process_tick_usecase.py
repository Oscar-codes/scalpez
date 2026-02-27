"""
Process Tick Use Case.

Caso de uso para procesar ticks de mercado.
Orquesta la construcción de velas, actualización de indicadores y generación de señales.

NOTA: Esta es una versión simplificada para Clean Architecture.
El ProcessTickUseCase completo en app/application/ sigue funcionando
para compatibilidad con el sistema actual.
"""

from __future__ import annotations

from typing import Optional, Callable, Awaitable
from dataclasses import dataclass

from backend.domain.value_objects.tick import Tick
from backend.domain.entities.candle import Candle
from backend.domain.services.indicator_calculator import IndicatorCalculator
from backend.application.ports.event_publisher import IEventPublisher


@dataclass
class ProcessTickResult:
    """Resultado del procesamiento de un tick."""
    tick_processed: bool = False
    candle_closed: Optional[Candle] = None
    indicators_updated: bool = False


class ProcessTickUseCase:
    """
    Caso de uso: Procesar tick de mercado.
    
    Versión simplificada que sigue Clean Architecture.
    Para la versión completa con CandleBuilder, MarketState, etc.,
    usar backend.app.application.process_tick_usecase.ProcessTickUseCase
    
    Este use case:
    1. Recibe un tick
    2. Lo pasa al builder de velas (callback)
    3. Si hay vela cerrada, calcula indicadores
    4. Publica eventos correspondientes
    """
    
    def __init__(
        self,
        indicator_calculator: IndicatorCalculator,
        event_publisher: IEventPublisher,
        candle_callback: Optional[Callable[[Tick], Awaitable[Optional[Candle]]]] = None,
    ):
        self._indicator_calc = indicator_calculator
        self._event_publisher = event_publisher
        self._candle_callback = candle_callback
        
        # Cache de precios para indicadores
        self._price_history: dict[str, list[float]] = {}
    
    async def execute(self, tick: Tick) -> ProcessTickResult:
        """
        Procesa un tick.
        
        Args:
            tick: Tick de mercado a procesar
        
        Returns:
            Resultado con información del procesamiento
        """
        result = ProcessTickResult(tick_processed=True)
        
        # Actualizar historial de precios
        if tick.symbol not in self._price_history:
            self._price_history[tick.symbol] = []
        self._price_history[tick.symbol].append(float(tick.price))
        
        # Limitar historial a últimos 500 precios
        if len(self._price_history[tick.symbol]) > 500:
            self._price_history[tick.symbol] = self._price_history[tick.symbol][-500:]
        
        # Si hay callback de vela, ejecutarlo
        if self._candle_callback:
            candle = await self._candle_callback(tick)
            if candle:
                result.candle_closed = candle
                result.indicators_updated = True
        
        return result
    
    def get_indicators(self, symbol: str) -> dict:
        """
        Calcula indicadores actuales para un símbolo.
        
        Args:
            symbol: Símbolo del activo
        
        Returns:
            Dict con indicadores calculados
        """
        prices = self._price_history.get(symbol, [])
        
        if len(prices) < 21:
            return {}
        
        return {
            "ema_9": self._indicator_calc.calculate_ema(prices, 9),
            "ema_21": self._indicator_calc.calculate_ema(prices, 21),
            "rsi_14": self._indicator_calc.calculate_rsi(prices, 14),
            "sma_20": self._indicator_calc.calculate_sma(prices, 20),
        }
