"""
QuantPulse – Presentation Layer
=================================
API HTTP y WebSocket.

Este módulo contiene:
- api/: FastAPI routes y schemas
- websocket/: WebSocket handlers

REGLA DE DEPENDENCIA:
Esta capa SOLO llama a use cases de application/.
NO accede directamente a domain/ ni infrastructure/.
"""

from backend.presentation.api.routes import router, init_routes
from backend.presentation.websocket.websocket_manager import WebSocketManager

__all__ = [
    "router",
    "init_routes",
    "WebSocketManager",
]
