"""
QuantPulse – API Schemas (Pydantic)
=====================================
Schemas de validación para request/response de la API REST.
Fase 1: schemas mínimos para estado y velas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class HealthResponse(BaseModel):
    status: str
    service: str


class CandleSchema(BaseModel):
    symbol: str
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    tick_count: int
    interval: int


class CandlesResponse(BaseModel):
    symbol: str
    count: int
    candles: List[CandleSchema]


class SymbolStatusSchema(BaseModel):
    last_price: float
    total_ticks: int
    total_candles: int
    candles_in_buffer: int
    has_active_trade: bool


class DerivClientStatusSchema(BaseModel):
    running: bool
    connected: bool
    ticks_received: int
    last_tick_time: float
    connected_since: float
    reconnect_attempts: int


class SystemStatusResponse(BaseModel):
    market_state: dict
    deriv_client: DerivClientStatusSchema
    ws_clients: int
