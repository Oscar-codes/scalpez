"""
QuantPulse – Presentation Layer
=================================
API HTTP y WebSocket.

Este módulo contiene:
- http/: FastAPI routes y schemas
- websocket/: WebSocket handlers

REGLA DE DEPENDENCIA:
Esta capa SOLO llama a use cases de application/.
NO accede directamente a domain/ ni infrastructure/.
"""
