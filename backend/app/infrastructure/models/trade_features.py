"""
QuantPulse – Trade Features ORM Model (ML Dataset)
===================================================
Modelo para la tabla `trade_features` - snapshot de features al momento de entrada.

═══════════════════════════════════════════════════════════════════════════════
PROPÓSITO CLAVE PARA MACHINE LEARNING
═══════════════════════════════════════════════════════════════════════════════

PROBLEMA DEL ML EN TRADING:
  Para entrenar un modelo supervisado necesitamos:
  
    X = features del momento de entrada (esto almacenamos aquí)
    y = resultado del trade (PROFIT=1, LOSS=0) (viene de trades.status)
  
  Pero los indicadores en memoria se sobrescriben cada tick.
  Sin persistencia, perdemos el contexto exacto de cada decisión.

SOLUCIÓN:
  trade_features captura el SNAPSHOT EXACTO del mercado al momento
  de entrada. Es el "antes" que permitirá predecir el "después".

CÓMO CREAR DATASET SUPERVISADO:
  
  SELECT 
    tf.ema_distance, tf.rsi_value, tf.rsi_slope, tf.volatility_20,
    tf.candle_body_ratio, tf.pattern_type, tf.distance_to_support,
    tf.distance_to_resistance, tf.market_structure_score,
    CASE WHEN t.status = 'PROFIT' THEN 1 ELSE 0 END AS label,
    t.pnl_percent
  FROM trade_features tf
  JOIN trades t ON t.id = tf.trade_id
  WHERE t.status IN ('PROFIT', 'LOSS')  -- Solo trades resueltos
  ORDER BY t.opened_at;

FEATURES DISEÑADAS:
  
  MOMENTUM:
    - ema_distance: (EMA9-EMA21)/price - normalizado, mide separación/convergencia
    - ema_slope_fast/slow: Derivada de EMAs - acelerando o desacelerando
  
  RSI:
    - rsi_value: Valor absoluto (0-100)
    - rsi_slope: delta vs anterior - momentum del momentum
    - rsi_zone: Categórica (OVERSOLD, NEUTRAL, OVERBOUGHT)
  
  VOLATILITY:
    - volatility_20: ATR 20 períodos - régimen de volatilidad
    - volatility_ratio: Actual vs promedio - alto/bajo relativo
  
  CANDLE:
    - candle_body_ratio: Body/Range (0-1) - fuerza de la vela
    - candle_direction: BULLISH, BEARISH, DOJI
    - candle_size_zscore: Tamaño relativo (z-score)
  
  STRUCTURE:
    - pattern_type: ema_cross, sr_bounce, breakout, etc.
    - conditions_count: Número de confirmaciones
    - distance_to_support/resistance: Contexto S/R
    - sr_quality_score: Fuerza del nivel
    - market_structure_score: Higher highs/lows (-1 a +1)
    - trend_alignment: WITH_TREND, COUNTER_TREND, NEUTRAL
  
  CONTEXT:
    - spread_estimate: Costo implícito
    - time_of_day_bucket: Hora (posible efecto)
    - day_of_week: Día (posible efecto)

═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, Integer, BigInteger, ForeignKey,
    Numeric, DateTime, Enum as SQLEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.models.trade import TradeModel


class TradeFeatureModel(Base):
    """
    Modelo ORM para features técnicas (snapshot al momento de entrada).
    
    RELACIÓN 1:1 CON TRADES:
    Cada trade tiene exactamente un registro de features.
    ON DELETE CASCADE: Si se borra el trade, se borran sus features.
    
    EXTENSIBILIDAD:
    Nuevos features → ALTER TABLE ADD COLUMN.
    No afecta tabla trades (separación de concerns).
    """
    
    __tablename__ = "trade_features"
    
    # ─── Primary Key ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    
    # ─── Foreign Key (1:1 con trades) ─────────────────────────────────
    trade_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    
    # ─── Momentum Features ────────────────────────────────────────────
    ema_distance: Mapped[Decimal] = mapped_column(
        Numeric(12, 8), nullable=False,
        comment="(EMA9-EMA21)/price normalizado"
    )
    ema_slope_fast: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), default=None,
        comment="Pendiente EMA9 (delta N velas)"
    )
    ema_slope_slow: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), default=None,
        comment="Pendiente EMA21"
    )
    
    # ─── RSI Features ─────────────────────────────────────────────────
    rsi_value: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False,
        comment="RSI 14 (0-100)"
    )
    rsi_slope: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 5), default=None,
        comment="RSI actual - RSI anterior"
    )
    rsi_zone: Mapped[str] = mapped_column(
        SQLEnum("OVERSOLD", "NEUTRAL", "OVERBOUGHT", name="rsi_zone_enum"),
        nullable=False
    )
    
    # ─── Volatility Features ──────────────────────────────────────────
    volatility_20: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 8), default=None,
        comment="ATR 20 períodos"
    )
    volatility_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 5), default=None,
        comment="Volatilidad actual / promedio"
    )
    
    # ─── Candle Features ──────────────────────────────────────────────
    candle_body_ratio: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False,
        comment="abs(close-open)/range (0-1)"
    )
    candle_direction: Mapped[str] = mapped_column(
        SQLEnum("BULLISH", "BEARISH", "DOJI", name="candle_direction_enum"),
        nullable=False
    )
    candle_size_zscore: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), default=None,
        comment="Tamaño relativo (z-score)"
    )
    
    # ─── Pattern & Structure ──────────────────────────────────────────
    pattern_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="ema_cross, sr_bounce, breakout, etc."
    )
    conditions_count: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Número de condiciones activas"
    )
    
    # ─── Support/Resistance Context ───────────────────────────────────
    distance_to_support: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), default=None,
        comment="(price-support)/price"
    )
    distance_to_resistance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), default=None,
        comment="(resistance-price)/price"
    )
    sr_quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 3), default=None,
        comment="Fuerza del nivel S/R (0-1)"
    )
    
    # ─── Market Structure ─────────────────────────────────────────────
    market_structure_score: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), default=None,
        comment="HH/HL ratio (-1 a +1)"
    )
    trend_alignment: Mapped[str | None] = mapped_column(
        SQLEnum("WITH_TREND", "COUNTER_TREND", "NEUTRAL", name="trend_alignment_enum"),
        default=None
    )
    
    # ─── Execution Context ────────────────────────────────────────────
    spread_estimate: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), default=None,
        comment="Spread estimado en el momento"
    )
    time_of_day_bucket: Mapped[int | None] = mapped_column(
        Integer, default=None,
        comment="Hora del día (0-23)"
    )
    day_of_week: Mapped[int | None] = mapped_column(
        Integer, default=None,
        comment="Día de semana (0-6, 0=Lunes)"
    )
    
    # ─── Metadata ─────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    
    # ─── Relationships ────────────────────────────────────────────────
    trade: Mapped["TradeModel"] = relationship(
        "TradeModel", back_populates="features"
    )
    
    # ─── Table Args ───────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_features_pattern", "pattern_type"),
        Index("idx_features_rsi", "rsi_zone", "rsi_value"),
    )
    
    # ─── Métodos ──────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """Serialización para export a ML."""
        return {
            "trade_id": self.trade_id,
            # Momentum
            "ema_distance": float(self.ema_distance),
            "ema_slope_fast": float(self.ema_slope_fast) if self.ema_slope_fast else None,
            "ema_slope_slow": float(self.ema_slope_slow) if self.ema_slope_slow else None,
            # RSI
            "rsi_value": float(self.rsi_value),
            "rsi_slope": float(self.rsi_slope) if self.rsi_slope else None,
            "rsi_zone": self.rsi_zone,
            # Volatility
            "volatility_20": float(self.volatility_20) if self.volatility_20 else None,
            "volatility_ratio": float(self.volatility_ratio) if self.volatility_ratio else None,
            # Candle
            "candle_body_ratio": float(self.candle_body_ratio),
            "candle_direction": self.candle_direction,
            "candle_size_zscore": float(self.candle_size_zscore) if self.candle_size_zscore else None,
            # Pattern
            "pattern_type": self.pattern_type,
            "conditions_count": self.conditions_count,
            # S/R
            "distance_to_support": float(self.distance_to_support) if self.distance_to_support else None,
            "distance_to_resistance": float(self.distance_to_resistance) if self.distance_to_resistance else None,
            "sr_quality_score": float(self.sr_quality_score) if self.sr_quality_score else None,
            # Structure
            "market_structure_score": float(self.market_structure_score) if self.market_structure_score else None,
            "trend_alignment": self.trend_alignment,
            # Context
            "spread_estimate": float(self.spread_estimate) if self.spread_estimate else None,
            "time_of_day_bucket": self.time_of_day_bucket,
            "day_of_week": self.day_of_week,
        }
    
    def to_ml_features(self) -> dict:
        """
        Retorna features en formato listo para modelo ML (sin NULLs problemáticos).
        Los valores None se reemplazan por 0 o valores default apropiados.
        """
        return {
            # Numéricos continuos
            "ema_distance": float(self.ema_distance),
            "ema_slope_fast": float(self.ema_slope_fast or 0),
            "ema_slope_slow": float(self.ema_slope_slow or 0),
            "rsi_value": float(self.rsi_value),
            "rsi_slope": float(self.rsi_slope or 0),
            "volatility_20": float(self.volatility_20 or 0),
            "volatility_ratio": float(self.volatility_ratio or 1),
            "candle_body_ratio": float(self.candle_body_ratio),
            "candle_size_zscore": float(self.candle_size_zscore or 0),
            "distance_to_support": float(self.distance_to_support or 0),
            "distance_to_resistance": float(self.distance_to_resistance or 0),
            "sr_quality_score": float(self.sr_quality_score or 0),
            "market_structure_score": float(self.market_structure_score or 0),
            "spread_estimate": float(self.spread_estimate or 0),
            "conditions_count": self.conditions_count,
            "time_of_day_bucket": self.time_of_day_bucket or 0,
            "day_of_week": self.day_of_week or 0,
            # Categóricas (para one-hot encoding)
            "rsi_zone": self.rsi_zone,
            "candle_direction": self.candle_direction,
            "pattern_type": self.pattern_type,
            "trend_alignment": self.trend_alignment or "NEUTRAL",
        }
    
    @classmethod
    def from_context(
        cls,
        trade_id: int,
        indicators: dict,
        candle,
        conditions: list,
        sr_context: dict = None,
        timestamp: datetime = None,
    ) -> "TradeFeatureModel":
        """
        Crea features desde el contexto del mercado al momento del trade.
        
        Args:
            trade_id: ID del trade en la BD
            indicators: Dict con ema_9, ema_21, rsi_14, prev_rsi, etc.
            candle: Vela cerrada que confirmó la señal
            conditions: Lista de condiciones activadas
            sr_context: Dict con support, resistance, volatility
            timestamp: Momento de la entrada (para time_of_day)
        """
        sr_context = sr_context or {}
        timestamp = timestamp or datetime.utcnow()
        
        # ── Calcular features de momentum ──
        ema_9 = indicators.get("ema_9", 0)
        ema_21 = indicators.get("ema_21", 0)
        price = candle.close if candle else ema_9
        
        ema_distance = (ema_9 - ema_21) / price if price > 0 else 0
        
        # ── RSI features ──
        rsi = indicators.get("rsi_14", 50)
        prev_rsi = indicators.get("prev_rsi", rsi)
        rsi_slope = rsi - prev_rsi
        
        if rsi < 35:
            rsi_zone = "OVERSOLD"
        elif rsi > 65:
            rsi_zone = "OVERBOUGHT"
        else:
            rsi_zone = "NEUTRAL"
        
        # ── Candle features ──
        if candle:
            candle_range = candle.high - candle.low
            body = abs(candle.close - candle.open)
            body_ratio = body / candle_range if candle_range > 0 else 0.5
            
            if candle.close > candle.open:
                direction = "BULLISH"
            elif candle.close < candle.open:
                direction = "BEARISH"
            else:
                direction = "DOJI"
        else:
            body_ratio = 0.5
            direction = "DOJI"
        
        # ── S/R Context ──
        support = sr_context.get("support", 0)
        resistance = sr_context.get("resistance", 0)
        
        dist_support = (price - support) / price if support > 0 and price > 0 else None
        dist_resistance = (resistance - price) / price if resistance > 0 and price > 0 else None
        
        # ── Pattern type ──
        pattern = conditions[0] if conditions else "unknown"
        
        return cls(
            trade_id=trade_id,
            # Momentum
            ema_distance=Decimal(str(round(ema_distance, 8))),
            ema_slope_fast=None,  # TODO: calcular con historial
            ema_slope_slow=None,
            # RSI
            rsi_value=Decimal(str(round(rsi, 3))),
            rsi_slope=Decimal(str(round(rsi_slope, 5))),
            rsi_zone=rsi_zone,
            # Volatility
            volatility_20=Decimal(str(sr_context.get("atr", 0))) if sr_context.get("atr") else None,
            volatility_ratio=None,  # TODO: calcular con promedio
            # Candle
            candle_body_ratio=Decimal(str(round(body_ratio, 4))),
            candle_direction=direction,
            candle_size_zscore=None,  # TODO: calcular con historial
            # Pattern
            pattern_type=pattern,
            conditions_count=len(conditions),
            # S/R
            distance_to_support=Decimal(str(round(dist_support, 8))) if dist_support else None,
            distance_to_resistance=Decimal(str(round(dist_resistance, 8))) if dist_resistance else None,
            sr_quality_score=None,  # TODO: calcular
            # Structure
            market_structure_score=None,  # TODO: calcular
            trend_alignment=None,  # TODO: calcular
            # Context
            spread_estimate=None,  # TODO: estimar
            time_of_day_bucket=timestamp.hour,
            day_of_week=timestamp.weekday(),
        )
    
    def __repr__(self) -> str:
        return (
            f"<TradeFeature(id={self.id}, trade_id={self.trade_id}, "
            f"pattern={self.pattern_type}, rsi={self.rsi_value})>"
        )
