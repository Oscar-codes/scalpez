"""
QuantPulse – Config helpers
===========================
Re-exporta settings y constantes derivadas para acceso conveniente.
"""

from backend.app.core.settings import settings

# Mapping de symbol_id → nombre legible para logs y frontend
SYMBOL_DISPLAY_NAMES: dict[str, str] = {
    "stpRNG": "Step Index",
    "R_100": "Volatility 100 (1s)",
    "R_75": "Volatility 75",
}

__all__ = ["settings", "SYMBOL_DISPLAY_NAMES"]
