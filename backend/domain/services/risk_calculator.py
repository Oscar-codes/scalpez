"""
QuantPulse – Domain Service: Risk Calculator
===============================================
Cálculos de gestión de riesgo puros.

Este servicio calcula Stop Loss, Take Profit, Risk-Reward
y validaciones de riesgo sin dependencias externas.

FÓRMULAS:
- SL: basado en swing high/low + buffer
- TP: basado en RR ratio objetivo
- RR: distancia TP / distancia SL
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from backend.domain.exceptions.domain_errors import RiskManagementError


@dataclass
class RiskConfig:
    """Configuración de gestión de riesgo."""
    
    rr_ratio: float = 2.0       # Risk-Reward objetivo
    min_rr: float = 1.5         # RR mínimo aceptable
    min_sl_pct: float = 0.0002  # SL mínimo como % del precio
    max_sl_pct: float = 0.02    # SL máximo como % del precio
    sl_buffer_pct: float = 0.0001  # Buffer adicional para SL


@dataclass
class RiskLevels:
    """Resultado del cálculo de niveles de riesgo."""
    
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    sl_distance: float
    tp_distance: float
    is_valid: bool
    rejection_reason: Optional[str] = None


class RiskCalculator:
    """
    Calculadora de niveles de riesgo.
    
    RESPONSABILIDAD:
    Calcular SL, TP y RR basado en el tipo de señal y niveles técnicos.
    
    NO tiene dependencias externas.
    """
    
    def __init__(self, config: RiskConfig = None):
        self._config = config or RiskConfig()
    
    def calculate_levels(
        self,
        signal_type: str,
        entry_price: float,
        swing_low: float,
        swing_high: float,
    ) -> RiskLevels:
        """
        Calcula SL, TP y RR para una señal.
        
        LÓGICA:
        - BUY:  SL debajo del swing_low, TP arriba del entry
        - SELL: SL encima del swing_high, TP debajo del entry
        
        Args:
            signal_type: "BUY" o "SELL"
            entry_price: Precio de entrada (close de vela confirmada)
            swing_low: Último swing low detectado
            swing_high: Último swing high detectado
        
        Returns:
            RiskLevels con todos los cálculos y validación
        """
        if signal_type == "BUY":
            return self._calculate_buy_levels(entry_price, swing_low, swing_high)
        else:
            return self._calculate_sell_levels(entry_price, swing_low, swing_high)
    
    def _calculate_buy_levels(
        self,
        entry: float,
        swing_low: float,
        swing_high: float,
    ) -> RiskLevels:
        """Calcula niveles para señal BUY."""
        # SL debajo del swing low con buffer
        buffer = entry * self._config.sl_buffer_pct
        stop_loss = swing_low - buffer
        
        # Distancia SL
        sl_distance = entry - stop_loss
        
        # Validar SL mínimo
        sl_pct = sl_distance / entry
        if sl_pct < self._config.min_sl_pct:
            return RiskLevels(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=0.0,
                rr=0.0,
                sl_distance=sl_distance,
                tp_distance=0.0,
                is_valid=False,
                rejection_reason="SL demasiado cercano",
            )
        
        # Validar SL máximo
        if sl_pct > self._config.max_sl_pct:
            return RiskLevels(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=0.0,
                rr=0.0,
                sl_distance=sl_distance,
                tp_distance=0.0,
                is_valid=False,
                rejection_reason="SL demasiado lejano",
            )
        
        # Calcular TP con RR objetivo
        tp_distance = sl_distance * self._config.rr_ratio
        take_profit = entry + tp_distance
        
        # Calcular RR real
        rr = tp_distance / sl_distance if sl_distance > 0 else 0.0
        
        # Validar RR mínimo
        is_valid = rr >= self._config.min_rr
        rejection_reason = None if is_valid else f"RR insuficiente: {rr:.2f} < {self._config.min_rr}"
        
        return RiskLevels(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            rr=rr,
            sl_distance=sl_distance,
            tp_distance=tp_distance,
            is_valid=is_valid,
            rejection_reason=rejection_reason,
        )
    
    def _calculate_sell_levels(
        self,
        entry: float,
        swing_low: float,
        swing_high: float,
    ) -> RiskLevels:
        """Calcula niveles para señal SELL."""
        # SL encima del swing high con buffer
        buffer = entry * self._config.sl_buffer_pct
        stop_loss = swing_high + buffer
        
        # Distancia SL
        sl_distance = stop_loss - entry
        
        # Validar SL mínimo
        sl_pct = sl_distance / entry
        if sl_pct < self._config.min_sl_pct:
            return RiskLevels(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=0.0,
                rr=0.0,
                sl_distance=sl_distance,
                tp_distance=0.0,
                is_valid=False,
                rejection_reason="SL demasiado cercano",
            )
        
        # Validar SL máximo
        if sl_pct > self._config.max_sl_pct:
            return RiskLevels(
                entry=entry,
                stop_loss=stop_loss,
                take_profit=0.0,
                rr=0.0,
                sl_distance=sl_distance,
                tp_distance=0.0,
                is_valid=False,
                rejection_reason="SL demasiado lejano",
            )
        
        # Calcular TP con RR objetivo
        tp_distance = sl_distance * self._config.rr_ratio
        take_profit = entry - tp_distance
        
        # Calcular RR real
        rr = tp_distance / sl_distance if sl_distance > 0 else 0.0
        
        # Validar RR mínimo
        is_valid = rr >= self._config.min_rr
        rejection_reason = None if is_valid else f"RR insuficiente: {rr:.2f} < {self._config.min_rr}"
        
        return RiskLevels(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            rr=rr,
            sl_distance=sl_distance,
            tp_distance=tp_distance,
            is_valid=is_valid,
            rejection_reason=rejection_reason,
        )
    
    def validate_signal_risk(
        self,
        levels: RiskLevels,
    ) -> bool:
        """
        Valida que los niveles de riesgo sean aceptables.
        
        Args:
            levels: Niveles calculados
        
        Returns:
            True si es válido, False si no
        
        Raises:
            RiskManagementError si hay violación crítica
        """
        if not levels.is_valid:
            return False
        
        if levels.rr < self._config.min_rr:
            raise RiskManagementError(
                f"RR {levels.rr:.2f} por debajo del mínimo {self._config.min_rr}",
                rule="min_rr"
            )
        
        return True
