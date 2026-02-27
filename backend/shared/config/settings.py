"""
QuantPulse – Settings (Pydantic BaseSettings)
=============================================
Configuración centralizada cargada desde variables de entorno / .env.
Se usa pydantic-settings para validación estricta al arranque.

NOTA: Este archivo se mueve de app/core/ a shared/config/ como parte
de la reestructuración Clean Architecture.
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
        default=5, description="Duración de la vela base en segundos"
    )
    max_candles_buffer: int = Field(
        default=200, description="Máximo de velas en memoria por símbolo por timeframe"
    )

    # ─── Timeframes ─────────────────────────────────────────────────────
    available_timeframes: List[str] = Field(
        default=["5m", "15m", "30m", "1h"],
        description="Marcos temporales disponibles para operar",
    )
    default_timeframe: str = Field(
        default="5m",
        description="Timeframe activo por defecto",
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

    # ─── Signal Engine ──────────────────────────────────────────────────
    signal_min_confirmations: int = Field(
        default=2, description="Mínimo de condiciones coincidentes para señal válida",
    )
    signal_rr_ratio: float = Field(
        default=2.0, description="Ratio Risk-Reward para calcular Take Profit",
    )
    signal_min_rr: float = Field(
        default=1.0, description="RR mínimo para aceptar una señal (1.0 = permite 1:1)",
    )
    signal_rsi_oversold: float = Field(
        default=35.0, description="Umbral RSI para condición de sobreventa",
    )
    signal_rsi_overbought: float = Field(
        default=65.0, description="Umbral RSI para condición de sobrecompra",
    )
    signal_min_sl_pct: float = Field(
        default=0.0002, description="Distancia mínima SL como fracción del precio",
    )
    signal_cooldown_candles: int = Field(
        default=3, description="Velas mínimas entre señales del mismo símbolo",
    )
    signal_sr_tolerance_pct: float = Field(
        default=0.0015, description="Tolerancia %% para rebote/rechazo en S/R",
    )
    signal_sr_max_levels: int = Field(
        default=10, description="Máximo de niveles S/R almacenados por símbolo",
    )
    signal_breakout_candle_mult: float = Field(
        default=1.2, description="Multiplicador tamaño vela para confirmar ruptura",
    )
    signal_consolidation_candles: int = Field(
        default=10, description="Velas para evaluar filtro de consolidación",
    )
    signal_consolidation_atr_mult: float = Field(
        default=2.0, description="Multiplicador ATR para filtro de consolidación",
    )

    # ─── Event Bus ──────────────────────────────────────────────────────
    event_bus_max_queue_size: int = Field(
        default=10_000,
        description="Tamaño máximo de cola del Event Bus para contrapresión",
    )

    # ─── Server ─────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8888)
    debug: bool = Field(default=False)

    # ─── MySQL Database ─────────────────────────────────────────────────
    db_host: str = Field(default="localhost", description="MySQL host")
    db_port: int = Field(default=3306, description="MySQL port")
    db_user: str = Field(default="quantpulse", description="MySQL username")
    db_password: str = Field(default="quantpulse_secret", description="MySQL password")
    db_name: str = Field(default="quantpulse", description="MySQL database name")
    db_echo: bool = Field(default=False, description="Loguear queries SQL (debug)")
    db_pool_size: int = Field(default=5, description="Conexiones en el pool")
    db_max_overflow: int = Field(default=10, description="Conexiones extra en picos")
    db_enabled: bool = Field(default=False, description="Habilitar persistencia MySQL")

    # ─── ML ─────────────────────────────────────────────────────────────
    ml_enabled: bool = Field(default=False, description="Habilitar filtrado ML")
    ml_threshold: float = Field(default=0.55, description="Umbral ML para emitir señales")
    ml_models_dir: str = Field(default="models", description="Directorio de modelos ML")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton global – se importa donde se necesite
settings = Settings()
