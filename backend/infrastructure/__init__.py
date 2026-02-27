"""
QuantPulse – Infrastructure Layer
===================================
Implementaciones concretas de interfaces.

Este módulo contiene:
- persistence/: Base de datos (MySQL)
- external/: APIs externas (Deriv, messaging)
- state/: Estado en memoria
- ml/: Machine Learning bounded context

REGLA DE DEPENDENCIA:
Esta capa implementa interfaces definidas en:
- domain/repositories/
- application/ports/

Puede importar de:
- domain/ (entidades, interfaces)
- application/ (ports)
- shared/ (config, logging)
"""
