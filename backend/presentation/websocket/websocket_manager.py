"""
Presentation – WebSocket Manager
=================================
Re-exporta WebSocketManager desde backend.app.api para compatibilidad.
"""

from backend.app.api.websocket_manager import WebSocketManager

__all__ = ["WebSocketManager"]
