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

=====================================
ESTADO DE IMPLEMENTACIÓN (v0.8)
=====================================
Última actualización: 27 de febrero de 2026

------------------------------------
✅ COMPLETADO
------------------------------------

**1) BACKEND (Python + FastAPI)**

│ Componente                    │ Estado │ Descripción                                                      │
├─────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
│ DerivClient                   │ ✅     │ Conexión WebSocket a Deriv con reconexión automática             │
│ EventBus                      │ ✅     │ Sistema pub/sub asíncrono para desacoplamiento de componentes    │
│ CandleBuilder                 │ ✅     │ Construcción de velas desde ticks (configurable: 5s, 15s, etc.)  │
│ IndicatorService              │ ✅     │ EMA 9, EMA 21, RSI 14 con cálculo incremental O(1)               │
│ SupportResistanceService      │ ✅     │ Detección dinámica de S/R, rupturas y consolidaciones            │
│ SignalEngine                  │ ✅     │ Generación de señales BUY/SELL con multi-confirmación (≥2 cond)  │
│ TradeSimulator                │ ✅     │ Paper trading con evaluación TP/SL/expiración por tick           │
│ StatsEngine                   │ ✅     │ 12+ métricas cuantitativas: WinRate, PF, Expectancy, Drawdown    │
│ TimeframeAggregator           │ ✅     │ Agregación de velas para múltiples timeframes (5s, 15s, 1m, 5m)  │
│ MarketState                   │ ✅     │ Estado centralizado del mercado con buffer de velas por símbolo  │
│ IndicatorState                │ ✅     │ Estado de indicadores por símbolo/timeframe                      │
│ TradeState                    │ ✅     │ Gestión de trades activos y cerrados                             │
│ ProcessTickUseCase            │ ✅     │ Orquestador: tick → vela → indicadores → señal → trade           │
│ WebSocketManager              │ ✅     │ Broadcast de eventos al frontend vía WebSocket                   │
│ REST API (/api/...)           │ ✅     │ Endpoints: candles, indicators, signals, trades, stats           │

**2) FRONTEND (Vanilla JS + ES6 Modules)**

│ Componente                    │ Estado │ Descripción                                                      │
├─────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
│ EventBus                      │ ✅     │ Sistema de eventos para comunicación entre componentes           │
│ StateManager                  │ ✅     │ Estado centralizado con reactivo a cambios                       │
│ WebSocketService              │ ✅     │ Conexión WS con reconexión automática y heartbeat                │
│ ApiService                    │ ✅     │ Cliente REST para fetch de datos                                 │
│ SymbolSelector                │ ✅     │ Selector de símbolo activo                                       │
│ TimeframeSelector             │ ✅     │ Selector de timeframe (5s, 15s, 1m, 5m)                          │
│ ChartComponent                │ ✅     │ Gráfico candlestick con Canvas + overlays EMA                    │
│ SignalPanel                   │ ✅     │ Panel de última señal con detalles y condiciones                 │
│ StatsPanel                    │ ✅     │ Panel de métricas de rendimiento                                 │
│ TradeTable                    │ ✅     │ Tabla de historial de trades simulados                           │
│ EquityCurve                   │ ✅     │ Gráfico de curva de equity                                       │
│ Sistema de Alertas Audio      │ ✅     │ Beeps via Web Audio API para señales y trades                    │

**3) ARQUITECTURA**

- Clean Architecture: domain → application → infrastructure → api
- Event-driven: desacoplamiento total entre componentes
- O(1) por tick: todos los cálculos son incrementales
- Anti-repainting: solo datos de velas cerradas
- Anti-duplicados: cooldown configurable entre señales
- Prepared for persistence: interfaces de repositorio listas

**4) INDICADORES IMPLEMENTADOS**

- EMA 9 (Exponential Moving Average - rápida)
- EMA 21 (Exponential Moving Average - lenta)
- RSI 14 (Relative Strength Index - Método Wilder)
- Swing Highs/Lows dinámicos
- Zonas de Soporte/Resistencia
- Detección de Rupturas (breakouts)
- Detección de Consolidación

**5) CONDICIONES DE SEÑAL**

1. ema_cross: Cruce de EMA9/EMA21 con confirmación de cambio de signo
2. rsi_reversal: RSI en zona extrema (<35 o >65) CON giro
3. sr_bounce: Rebote en soporte/resistencia con vela confirmadora
4. breakout: Ruptura de nivel S/R con vela fuerte (rango > 1.2× promedio)

**6) MÉTRICAS DE RENDIMIENTO**

- Total trades
- Win Rate / Loss Rate
- Profit Factor
- Expectancy
- Average Win / Average Loss
- Average RR Real
- Equity Curve
- Max Drawdown
- Best/Worst Trade
- Recovery Factor

------------------------------------
🔄 EN PROGRESO
------------------------------------

│ Feature                       │ Estado │ Notas                                                            │
├─────────────────────────────────┼────────┼───────────────────────────────────────────────────────────────────┤
│ Filtros en TradeTable         │ 🔄     │ Filtro por símbolo implementado, falta por resultado             │
│ Parámetros editables UI       │ 🔄     │ Backend configurable, falta panel de settings en frontend        │

------------------------------------
📋 PENDIENTE
------------------------------------

│ Feature                       │ Prioridad │ Descripción                                                   │
├─────────────────────────────────┼───────────┼────────────────────────────────────────────────────────────────┤
│ Persistencia (SQLite/Postgres)│ Media     │ Guardar trades/señales para análisis histórico                │
│ Patrones clásicos             │ Baja      │ Doble techo/suelo (opcional, las 4 condiciones dan buen edge) │
│ Backtesting module            │ Baja      │ Evaluar estrategia sobre datos históricos                     │
│ Automatización real           │ Futura    │ Ejecución real de órdenes vía API Deriv                       │
│ Notificaciones push           │ Baja      │ Alertas via Telegram/Discord                                  │

------------------------------------
📁 ESTRUCTURA DEL PROYECTO
------------------------------------

```
scalpez/
├── backend/
│   ├── main.py                 # Entry point + composición
│   └── app/
│       ├── api/                # HTTP routes + WebSocket
│       ├── application/        # Use cases (orchestración)
│       ├── core/               # Config + logging + settings
│       ├── domain/             # Entities + Value Objects
│       │   └── entities/
│       │       └── value_objects/
│       ├── infrastructure/     # DerivClient + EventBus + DB
│       │   └── repositories/
│       ├── services/           # Business logic (indicators, signals, etc.)
│       └── state/              # State managers (market, indicators, trades)
├── frontend/
│   ├── index.html              # Dashboard SPA
│   ├── css/styles.css          # Estilos custom
│   ├── js/
│   │   ├── app.js              # Orchestrador
│   │   ├── core/               # EventBus, StateManager
│   │   ├── services/           # WS + API clients
│   │   └── components/         # UI components
│   └── assets/                 # Bootstrap + recursos
├── test/                       # Unit tests
└── doc/                        # PRD + documentación
```

------------------------------------
🚀 CÓMO EJECUTAR
------------------------------------

# Backend
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8888

# Frontend
# Abrir http://localhost:8888 en el navegador
# (El backend sirve los archivos estáticos del frontend)