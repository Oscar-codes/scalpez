"""
QuantPulse – Domain Entity: Trade (Paper Trading)
=====================================================
Trade simulado inmutable (una vez cerrado) para paper trading en tiempo real.

═══════════════════════════════════════════════════════════════
            CICLO DE VIDA DEL TRADE
═══════════════════════════════════════════════════════════════

  Signal generada (vela N cierra)
       │
       ▼
  Trade PENDING ──(siguiente tick)──▸ Trade OPEN (entry al precio del tick)
       │
       ├── Cada tick evalúa SL / TP
       │
       ├── precio cruza TP ──▸ PROFIT
       ├── precio cruza SL ──▸ LOSS
       └── 30 min expiran ──▸ EXPIRED (cierra al precio actual)

DECISIONES DE DISEÑO:

POR QUÉ NO frozen=True:
  A diferencia de Signal (que es un evento puntual), un Trade tiene
  un ciclo de vida mutable: pasa de PENDING → OPEN → cerrado.
  Se usa una clase con setters controlados. Una vez cerrado,
  to_dict() captura el estado final inmutable para API/persistencia.

CÓMO SE EVITA LOOK-AHEAD BIAS:
  La señal se genera en vela N con close=X. Pero el trade NO se
  ejecuta a precio X. Se coloca en estado PENDING y se ejecuta
  al precio del SIGUIENTE tick (o vela). Esto modela la realidad:
  no puedes comprar al precio de cierre de una vela que ya cerró.

  Entry real = precio del primer tick POSTERIOR a la señal.

CÁLCULO DE PnL:

  BUY:
      pnl% = ((close_price - entry_price) / entry_price) × 100

      Ejemplo: entry=100, close=102 → (102-100)/100 × 100 = +2.00%
      Ejemplo: entry=100, close=98  → (98-100)/100 × 100  = -2.00%

  SELL:
      pnl% = ((entry_price - close_price) / entry_price) × 100

      Ejemplo: entry=100, close=98  → (100-98)/100 × 100  = +2.00%
      Ejemplo: entry=100, close=102 → (100-102)/100 × 100 = -2.00%

  JUSTIFICACIÓN:
      Dividir por entry_price normaliza el PnL independientemente
      del rango de precios del instrumento. Un +1% en R_100 (825)
      y un +1% en R_75 (37000) representan el mismo rendimiento
      proporcional, permitiendo comparación directa entre símbolos.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum


class TradeStatus(str, Enum):
    """Estados posibles de un trade simulado."""
    PENDING = "PENDING"  # Señal recibida, esperando entry
    OPEN = "OPEN"        # Ejecutado, monitoreando
    PROFIT = "PROFIT"    # Cerrado por Take Profit
    LOSS = "LOSS"        # Cerrado por Stop Loss
    EXPIRED = "EXPIRED"  # Cerrado por expiración temporal


class SimulatedTrade:
    """
    Trade simulado con ciclo de vida completo.

    Métodos controlados para transición de estado:
      - activate()  → PENDING → OPEN
      - close()     → OPEN → PROFIT|LOSS|EXPIRED

    Una vez cerrado, no se puede modificar.
    """

    __slots__ = (
        "id", "symbol", "signal_type", "signal_id",
        "signal_entry", "stop_loss", "take_profit", "rr",
        "entry_price", "close_price",
        "status", "open_timestamp", "close_timestamp",
        "pnl_percent", "duration_seconds",
        "conditions", "max_duration_seconds",
    )

    def __init__(
        self,
        symbol: str,
        signal_type: str,
        signal_id: str,
        signal_entry: float,
        stop_loss: float,
        take_profit: float,
        rr: float,
        conditions: tuple,
        max_duration_seconds: int = 1800,
    ) -> None:
        self.id: str = uuid.uuid4().hex[:12]
        self.symbol = symbol
        self.signal_type = signal_type     # "BUY" | "SELL"
        self.signal_id = signal_id         # ID de la señal origen

        # Precios objetivo (de la señal)
        self.signal_entry = signal_entry   # Entry sugerido por la señal
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.rr = rr
        self.conditions = conditions

        # Precios reales (se llenan al activar/cerrar)
        self.entry_price: float = 0.0
        self.close_price: float = 0.0

        # Estado
        self.status: TradeStatus = TradeStatus.PENDING
        self.open_timestamp: float = 0.0
        self.close_timestamp: float = 0.0

        # Resultado
        self.pnl_percent: float = 0.0
        self.duration_seconds: float = 0.0
        self.max_duration_seconds = max_duration_seconds

    # ════════════════════════════════════════════════════════════════
    #  TRANSICIONES DE ESTADO
    # ════════════════════════════════════════════════════════════════

    def activate(self, entry_price: float, timestamp: float) -> None:
        """
        Transición PENDING → OPEN.

        Se ejecuta al precio del PRIMER TICK posterior a la señal,
        NO al precio de cierre de la vela que generó la señal.

        CÓMO SE EVITA LOOK-AHEAD BIAS:
        La señal dice "entry sugerido = close de vela N", pero en la
        realidad no puedes comprar al precio de cierre de una vela que
        ya cerró. El primer tick disponible DESPUÉS de la señal es el
        precio real de ejecución. Puede haber slippage (entry_price ≠
        signal_entry), lo cual es realista.
        """
        assert self.status == TradeStatus.PENDING, \
            f"activate() solo desde PENDING, actual={self.status}"

        self.entry_price = entry_price
        self.open_timestamp = timestamp
        self.status = TradeStatus.OPEN

    def close(
        self,
        close_price: float,
        status: TradeStatus,
        timestamp: float,
    ) -> None:
        """
        Transición OPEN → PROFIT|LOSS|EXPIRED.

        Calcula PnL y duración automáticamente.

        MATEMÁTICA DEL PnL:
          BUY:  pnl% = ((close - entry) / entry) × 100
          SELL: pnl% = ((entry - close) / entry) × 100

        PROTECCIÓN:
        - Se calcula una sola vez (assert status == OPEN).
        - Una vez cerrado, el trade es efectivamente inmutable.
        """
        assert self.status == TradeStatus.OPEN, \
            f"close() solo desde OPEN, actual={self.status}"
        assert status in (TradeStatus.PROFIT, TradeStatus.LOSS, TradeStatus.EXPIRED), \
            f"Status de cierre inválido: {status}"

        self.close_price = close_price
        self.status = status
        self.close_timestamp = timestamp
        self.duration_seconds = timestamp - self.open_timestamp

        # ── Calcular PnL ──
        if self.entry_price != 0:
            if self.signal_type == "BUY":
                self.pnl_percent = (
                    (close_price - self.entry_price) / self.entry_price
                ) * 100.0
            else:  # SELL
                self.pnl_percent = (
                    (self.entry_price - close_price) / self.entry_price
                ) * 100.0

    # ════════════════════════════════════════════════════════════════
    #  CONSULTAS
    # ════════════════════════════════════════════════════════════════

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def is_pending(self) -> bool:
        return self.status == TradeStatus.PENDING

    @property
    def is_closed(self) -> bool:
        return self.status in (
            TradeStatus.PROFIT, TradeStatus.LOSS, TradeStatus.EXPIRED,
        )

    @property
    def is_expired(self) -> bool:
        """¿Excedió la duración máxima?"""
        if self.status != TradeStatus.OPEN:
            return False
        return (time.time() - self.open_timestamp) >= self.max_duration_seconds

    def to_dict(self) -> dict:
        """Serialización para API / WebSocket / persistencia futura."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "signal_id": self.signal_id,
            "signal_entry": round(self.signal_entry, 5),
            "entry_price": round(self.entry_price, 5),
            "stop_loss": round(self.stop_loss, 5),
            "take_profit": round(self.take_profit, 5),
            "rr": round(self.rr, 2),
            "close_price": round(self.close_price, 5) if self.close_price else None,
            "status": self.status.value,
            "open_timestamp": self.open_timestamp,
            "close_timestamp": self.close_timestamp or None,
            "pnl_percent": round(self.pnl_percent, 4) if self.is_closed else None,
            "duration_seconds": round(self.duration_seconds, 1) if self.is_closed else None,
            "conditions": list(self.conditions),
        }
