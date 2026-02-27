Actúa como un desarrollador senior full-stack especializado en trading algorítmico, scalping y análisis técnico avanzado usando la API WebSocket de Deriv.

OBJETIVO:
Construir una aplicación web que se conecte vía WebSocket a Deriv y muestre en tiempo real:

- Step Index
- Volatility 100 
- Volatility 10
- Volatility 75

Además debe incluir:
- Sistema de alertas inteligentes.
- Simulación automática de resultados (paper trading).
- Historial completo de señales no ejecutadas.
- Enfoque en scalping con RR entre 1:1 y 1:3.
- Duración estimada de trades entre 15 y 30 minutos.

------------------------------------
1) CONEXIÓN
------------------------------------
- Endpoint oficial: wss://ws.derivws.com/websockets/v3
- Suscripción a ticks en tiempo real.
- Reconexión automática con backoff exponencial.
- Manejo robusto de errores.

------------------------------------
2) SISTEMA DE SEÑALES (SCALPING)
------------------------------------

Generar señales BUY / SELL / NEUTRAL basadas en confirmación múltiple:

Indicadores:
- EMA 9 y EMA 21
- RSI 14
- Soportes y resistencias dinámicos
- Rupturas
- Patrones: doble techo, doble suelo, consolidación

Condición:
La señal solo se activa si al menos 2-3 condiciones coinciden.

------------------------------------
3) GESTIÓN DE TRADE SIMULADO
------------------------------------

Cuando se genera una señal:

El sistema debe calcular automáticamente:

- Precio de entrada.
- Stop Loss técnico (por debajo de soporte o swing low).
- Take Profit basado en RR configurable (1:1, 1:2 o 1:3).
- Tiempo máximo de operación: 30 minutos.

Si el usuario NO ejecuta la operación real, el sistema debe:

- Monitorear el precio automáticamente.
- Determinar si primero se alcanzó:
      → Take Profit (Profit)
      → Stop Loss (Loss)
      → Expiración por tiempo.

Guardar el resultado en un historial.

------------------------------------
4) HISTORIAL DE ALERTAS NO EJECUTADAS
------------------------------------

Crear un panel que muestre:

- Fecha y hora
- Activo
- Tipo (BUY/SELL)
- Entry
- Stop Loss
- Take Profit
- RR utilizado
- Resultado final:
      - Profit
      - Stop Loss
      - Expirado
- Duración real del trade
- % de movimiento

Mostrar estadísticas:

- Win rate
- Profit factor
- R:R promedio real
- Total señales
- Señales ganadoras
- Señales perdedoras

------------------------------------
5) INTERFAZ
------------------------------------

- Dashboard principal con precios en tiempo real.
- Mini gráfico candlestick.
- Panel de señal actual.
- Historial de señales simuladas.
- Filtro por activo.
- Filtro por resultado.
- Parámetros editables (RSI, EMA, RR).

------------------------------------
6) EXPLICAR EN EL CÓDIGO
------------------------------------

- Cómo se calcula cada indicador matemáticamente.
- Cómo se determina el Stop Loss técnico.
- Cómo se valida el RR.
- Cómo se simula el resultado sin ejecutar orden real.
- Cómo evitar repainting o señales falsas.

------------------------------------
7) ENTREGAR
------------------------------------

- Código completo funcional.
- Estructura del proyecto.
- Arquitectura escalable.
- Buenas prácticas de rendimiento.
- Manejo eficiente de memoria.
- Preparado para futura automatización real.

No des teoría innecesaria. Entrega código estructurado y profesional.