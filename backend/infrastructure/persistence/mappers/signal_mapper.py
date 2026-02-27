"""
QuantPulse – Signal Mapper
============================
Mapea entre Signal (domain entity) y SignalModel (ORM).

Este mapper es CRÍTICO para Clean Architecture:
- El domain NO conoce SQLAlchemy
- El ORM Model NO tiene lógica de negocio
- El mapper traduce entre ambos mundos
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional

from backend.domain.entities.signal import Signal


class SignalMapper:
    """
    Mapper bidireccional Signal ↔ SignalModel.
    
    USO:
        mapper = SignalMapper()
        
        # Entity → Model
        model = mapper.to_model(signal, symbol_id, indicators)
        
        # Model → Entity
        entity = mapper.to_entity(model)
    """
    
    def to_model(
        self,
        signal: Signal,
        symbol_id: int,
        indicators: Dict[str, float] = None,
    ) -> Dict[str, Any]:
        """
        Convierte Signal entity a dict para crear SignalModel.
        
        NOTA: Retorna dict en lugar de SignalModel para evitar
        importar el modelo en este archivo (dependency direction).
        El repositorio usará este dict para crear el modelo.
        
        Args:
            signal: Entidad de dominio
            symbol_id: ID del símbolo en BD
            indicators: Dict con EMA, RSI, etc.
        
        Returns:
            Dict con campos para SignalModel
        """
        indicators = indicators or {}
        
        return {
            "uuid": signal.id,
            "symbol_id": symbol_id,
            "signal_type": signal.signal_type,
            "entry_price": Decimal(str(round(signal.entry, 8))),
            "stop_loss": Decimal(str(round(signal.stop_loss, 8))),
            "take_profit": Decimal(str(round(signal.take_profit, 8))),
            "rr_ratio": Decimal(str(round(signal.rr, 4))),
            "confidence": signal.confidence,
            "conditions": list(signal.conditions),
            "created_at": datetime.fromtimestamp(signal.timestamp),
            "candle_timestamp": datetime.fromtimestamp(signal.candle_timestamp),
            "estimated_duration": int(signal.estimated_duration),
            
            # Indicadores opcionales
            "ema9": Decimal(str(indicators.get("ema9", 0))),
            "ema21": Decimal(str(indicators.get("ema21", 0))),
            "rsi": Decimal(str(indicators.get("rsi", 0))),
            "pattern_detected": indicators.get("pattern"),
        }
    
    def to_entity(self, model_data: Dict[str, Any]) -> Signal:
        """
        Convierte datos de SignalModel a Signal entity.
        
        Args:
            model_data: Dict con campos del modelo ORM
        
        Returns:
            Signal entity de dominio
        """
        # Convertir conditions si es string JSON
        conditions = model_data.get("conditions", [])
        if isinstance(conditions, str):
            import json
            conditions = json.loads(conditions)
        
        # Convertir timestamps
        timestamp = model_data.get("created_at")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()
        
        candle_ts = model_data.get("candle_timestamp")
        if isinstance(candle_ts, datetime):
            candle_ts = candle_ts.timestamp()
        
        return Signal(
            id=model_data["uuid"],
            symbol=model_data.get("symbol_name", ""),  # Viene del JOIN
            signal_type=model_data["signal_type"],
            entry=float(model_data["entry_price"]),
            stop_loss=float(model_data["stop_loss"]),
            take_profit=float(model_data["take_profit"]),
            rr=float(model_data["rr_ratio"]),
            timestamp=timestamp or 0.0,
            candle_timestamp=candle_ts or 0.0,
            conditions=tuple(conditions),
            confidence=model_data.get("confidence", len(conditions)),
            estimated_duration=float(model_data.get("estimated_duration", 0)),
        )
    
    def to_entity_from_orm(self, model: Any, symbol_name: str = "") -> Signal:
        """
        Convierte SignalModel ORM directamente a Signal entity.
        
        Args:
            model: Instancia de SignalModel ORM
            symbol_name: Nombre del símbolo (resuelto desde relación)
        
        Returns:
            Signal entity
        """
        conditions = model.conditions or []
        if isinstance(conditions, str):
            import json
            conditions = json.loads(conditions)
        
        timestamp = model.created_at.timestamp() if model.created_at else 0.0
        candle_ts = model.candle_timestamp.timestamp() if model.candle_timestamp else 0.0
        
        return Signal(
            id=model.uuid,
            symbol=symbol_name or (model.symbol.name if hasattr(model, 'symbol') else ""),
            signal_type=model.signal_type,
            entry=float(model.entry_price),
            stop_loss=float(model.stop_loss),
            take_profit=float(model.take_profit),
            rr=float(model.rr_ratio),
            timestamp=timestamp,
            candle_timestamp=candle_ts,
            conditions=tuple(conditions),
            confidence=model.confidence or len(conditions),
            estimated_duration=float(model.estimated_duration or 0),
        )
