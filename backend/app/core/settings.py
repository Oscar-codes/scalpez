"""
QuantPulse – Settings (Pydantic BaseSettings)
=============================================
Configuración centralizada cargada desde variables de entorno / .env.
Se usa pydantic-settings para validación estricta al arranque.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # ─── Deriv WebSocket ────────────────────────────────────────────────
    deriv_app_id: str = Field(default="1089", description="App ID registrado en Deriv")
    deriv_ws_url: str = Field(
        default="wss://ws.derivws.com/websockets/v3",
        description="WebSocket endpoint de Deriv",
    )

    # Símbolos a suscribir (Deriv symbol IDs)
    deriv_symbols: List[str] = Field(
        default=["stpRNG", "R_100", "R_75"],
        description="Step Index, Volatility 100 (1s), Volatility 75",
    )

    # ─── Candle Builder ─────────────────────────────────────────────────
    candle_interval_seconds: int = Field(
        default=5, description="Duración de cada vela en segundos"
    )
    max_candles_buffer: int = Field(
        default=200, description="Máximo de velas en memoria por símbolo"
    )

    # ─── Reconexión ─────────────────────────────────────────────────────
    ws_reconnect_base_delay: float = Field(
        default=1.0, description="Delay base (seg) para backoff exponencial"
    )
    ws_reconnect_max_delay: float = Field(
        default=60.0, description="Delay máximo (seg) entre reconexiones"
    )
    ws_heartbeat_interval: int = Field(
        default=30, description="Intervalo (seg) de ping/heartbeat a Deriv"
    )

    # ─── Trading (futuro) ───────────────────────────────────────────────
    rr_default: float = Field(default=2.0, description="Risk-Reward ratio por defecto")
    max_trade_duration: int = Field(
        default=30, description="Duración máxima de trade en minutos"
    )

    # ─── Event Bus ──────────────────────────────────────────────────────
    event_bus_max_queue_size: int = Field(
        default=10_000,
        description="Tamaño máximo de cola del Event Bus para contrapresión",
    )

    # ─── Server ─────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton global – se importa donde se necesite
settings = Settings()
