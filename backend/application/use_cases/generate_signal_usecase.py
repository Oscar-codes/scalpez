"""
Generate Signal Use Case.

Caso de uso para generar señales de trading.
Orquesta los domain services y publica eventos según Clean Architecture.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from backend.domain.entities.signal import Signal
from backend.domain.entities.candle import Candle
from backend.domain.repositories.signal_repository import ISignalRepository
from backend.domain.services.signal_rules import SignalRules
from backend.domain.services.risk_calculator import RiskCalculator
from backend.domain.events.domain_events import SignalGenerated, SignalFiltered
from backend.application.ports.event_publisher import IEventPublisher
from backend.application.ports.ml_predictor import IMLPredictor, PredictionResult
from backend.application.dto.signal_dto import SignalRequestDTO, SignalResponseDTO


@dataclass
class GenerateSignalResult:
    """Resultado de la generación de señal."""
    signal: Optional[Signal] = None
    generated: bool = False
    filtered: bool = False
    filter_reason: Optional[str] = None


class GenerateSignalUseCase:
    """
    Caso de uso: Generar señal de trading.
    
    Orquesta:
    1. Evaluación de reglas de señal (SignalRules)
    2. Cálculo de gestión de riesgo (RiskCalculator)
    3. Filtrado ML opcional
    4. Persistencia y publicación de eventos
    
    DEPENDE SOLO DE:
    - Interfaces de repositorio (ISignalRepository)
    - Interfaces de puertos (IEventPublisher, IMLPredictor)
    - Domain services puros (SignalRules, RiskCalculator)
    """
    
    def __init__(
        self,
        signal_repository: ISignalRepository,
        event_publisher: IEventPublisher,
        signal_rules: SignalRules,
        risk_calculator: RiskCalculator,
        ml_predictor: Optional[IMLPredictor] = None,
    ):
        self._signal_repo = signal_repository
        self._event_publisher = event_publisher
        self._signal_rules = signal_rules
        self._risk_calculator = risk_calculator
        self._ml_predictor = ml_predictor
    
    async def execute(
        self,
        request: SignalRequestDTO,
    ) -> GenerateSignalResult:
        """
        Ejecuta la generación de señal.
        
        Args:
            request: DTO con datos para evaluar la señal
        
        Returns:
            Resultado con la señal generada o razón de filtrado
        """
        # 1. Evaluar reglas de señal
        signal_type, conditions = self._evaluate_rules(request)
        
        if signal_type is None:
            return GenerateSignalResult(generated=False)
        
        # 2. Calcular risk management
        entry = request.current_price
        sl, tp, rr = self._risk_calculator.calculate_sl_tp(
            entry=entry,
            signal_type=signal_type,
            atr=request.atr,
            support=request.support,
            resistance=request.resistance,
        )
        
        # Validar R:R mínimo
        min_rr = 1.5  # Configurable
        if rr < min_rr:
            return GenerateSignalResult(
                generated=False,
                filtered=True,
                filter_reason=f"R:R {rr:.2f} < mínimo {min_rr}",
            )
        
        # 3. Crear entidad Signal
        import time
        signal = Signal(
            symbol=request.symbol,
            signal_type=signal_type,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            rr=rr,
            timestamp=time.time(),
            candle_timestamp=request.candle_timestamp,
            conditions=tuple(conditions),
            confidence=len(conditions),
            estimated_duration=self._estimate_duration(request.timeframe),
        )
        
        # 4. Filtrado ML opcional
        if self._ml_predictor is not None:
            ml_result = await self._apply_ml_filter(signal, request)
            if ml_result.filtered:
                # Publicar evento de filtrado
                await self._event_publisher.publish(
                    SignalFiltered(
                        signal_id=signal.id,
                        filter_type="ml",
                        reason=ml_result.filter_reason or "ML confidence bajo",
                    )
                )
                return ml_result
            # Actualizar confidence con predicción ML
            signal.confidence = ml_result.signal.confidence if ml_result.signal else signal.confidence
        
        # 5. Persistir señal
        await self._signal_repo.save(signal)
        
        # 6. Publicar evento
        await self._event_publisher.publish(
            SignalGenerated(signal=signal)
        )
        
        return GenerateSignalResult(
            signal=signal,
            generated=True,
        )
    
    def _evaluate_rules(
        self,
        request: SignalRequestDTO,
    ) -> tuple[Optional[str], List[str]]:
        """Evalúa las reglas de señal."""
        conditions = []
        
        # EMA Cross
        if request.ema_fast and request.ema_slow:
            ema_cross = self._signal_rules.check_ema_cross(
                request.ema_fast, 
                request.ema_slow,
                request.prev_ema_fast,
                request.prev_ema_slow,
            )
            if ema_cross:
                conditions.append(f"ema_cross_{ema_cross}")
        
        # RSI Reversal
        if request.rsi:
            rsi_signal = self._signal_rules.check_rsi_reversal(
                request.rsi,
                request.prev_rsi,
            )
            if rsi_signal:
                conditions.append(f"rsi_reversal_{rsi_signal}")
        
        # S/R Bounce
        if request.support and request.resistance:
            sr_signal = self._signal_rules.check_sr_bounce(
                price=request.current_price,
                support=request.support,
                resistance=request.resistance,
                atr=request.atr,
            )
            if sr_signal:
                conditions.append(f"sr_bounce_{sr_signal}")
        
        # Determinar tipo de señal por mayoría
        if not conditions:
            return None, []
        
        buy_signals = sum(1 for c in conditions if c.endswith("_BUY"))
        sell_signals = sum(1 for c in conditions if c.endswith("_SELL"))
        
        if buy_signals > sell_signals:
            return "BUY", conditions
        elif sell_signals > buy_signals:
            return "SELL", conditions
        else:
            return None, []
    
    async def _apply_ml_filter(
        self,
        signal: Signal,
        request: SignalRequestDTO,
    ) -> GenerateSignalResult:
        """Aplica filtrado ML."""
        if self._ml_predictor is None:
            return GenerateSignalResult(signal=signal, generated=True)
        
        features = {
            "ema_fast": request.ema_fast,
            "ema_slow": request.ema_slow,
            "rsi": request.rsi,
            "atr": request.atr,
            "price": request.current_price,
            "signal_type": signal.signal_type,
        }
        
        prediction = await self._ml_predictor.predict(signal.symbol, features)
        
        if prediction.confidence < 0.5:
            return GenerateSignalResult(
                filtered=True,
                filter_reason=f"ML confidence {prediction.confidence:.2f} < 0.5",
            )
        
        # Boost confidence con predicción ML
        new_confidence = signal.confidence + (prediction.confidence * 2)
        
        # Crear nueva señal con confidence actualizado
        boosted_signal = Signal(
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
            confidence=new_confidence,
            estimated_duration=signal.estimated_duration,
        )
        
        return GenerateSignalResult(signal=boosted_signal, generated=True)
    
    def _estimate_duration(self, timeframe: str) -> float:
        """Estima duración del trade basado en timeframe."""
        durations = {
            "5s": 30.0,
            "1m": 300.0,
            "5m": 900.0,
            "15m": 2700.0,
        }
        return durations.get(timeframe, 300.0)
