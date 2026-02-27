"""
QuantPulse – Infrastructure Layer
===================================
Implementaciones concretas de interfaces.

Este módulo contiene:
- persistence/: Base de datos (MySQL)
- external/: APIs externas (Deriv)

REGLA DE DEPENDENCIA:
Esta capa implementa interfaces definidas en:
- domain/repositories/
- application/ports/

Puede importar de:
- domain/ (entidades, interfaces)
- application/ (ports)
- shared/ (config, logging)

Nota: ML vive en backend/ml/ como bounded context separado.
"""
