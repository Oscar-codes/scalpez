# 🏗️ INFORME DE AUDITORÍA ARQUITECTÓNICA
## QuantPulse Backend - Clean Architecture & DDD Analysis

**Fecha:** $(Get-Date)  
**Analizado por:** Software Architect Senior  
**Versión del análisis:** 1.0

---

## 📊 RESUMEN EJECUTIVO

### Estado Crítico Detectado: ARQUITECTURA DUAL NO INTEGRADA

El backend presenta una **duplicación arquitectónica severa**: existen dos sistemas paralelos en funcionamiento:

| Sistema | Ubicación | Líneas de Código | Estado |
|---------|-----------|-----------------|--------|
| **Legacy** | `backend/app/` | ~6,300 líneas | ✅ EN USO (main.py) |
| **Clean Architecture** | `backend/domain/`, `application/`, `infrastructure/` | ~3,500 líneas | ⚠️ NO CONECTADO |
| **ML Bounded Context** | `backend/ml/` | ~2,900 líneas | ✅ Semi-aislado |
| **DI Container** | `backend/container.py` | 289 líneas | ❌ NO USADO |

**Impacto:** Mantenimiento duplicado, confusión de responsabilidades, código muerto, y la refactorización Clean Architecture NO está siendo ejecutada en producción.

---

## 🔴 1. PAQUETES ELIMINABLES (Dead Code)

### 1.1 Archivos Placeholder (4 líneas - stubs vacíos)
Estos archivos contienen solo un docstring y un `pass`:

| Archivo | Líneas | Justificación |
|---------|--------|---------------|
| `backend/app/application/generate_signal_usecase.py` | 4 | Stub vacío, funcionalidad en signal_engine.py |
| `backend/app/application/simulate_trade_usecase.py` | 4 | Stub vacío, funcionalidad en trade_simulator.py |
| `backend/app/application/stats_usecase.py` | 4 | Stub vacío, funcionalidad en stats_engine.py |
| `backend/app/services/pattern_detector.py` | 4 | Stub vacío, nunca implementado |

**Acción:** ✂️ ELIMINAR inmediatamente - 0 impacto

### 1.2 Directorios Vacíos (solo `__init__.py` con 1 línea)

| Directorio | Contenido | Justificación |
|------------|-----------|---------------|
| `backend/infrastructure/external/deriv/` | Solo `__init__.py` | Adapter real está en `deriv_adapter.py` |
| `backend/infrastructure/external/messaging/` | Solo `__init__.py` | No implementado |
| `backend/infrastructure/ml/training/` | Solo `__init__.py` | Training real está en `backend/ml/` |
| `backend/infrastructure/ml/registry/` | Solo `__init__.py` | Registry real está en `backend/ml/` |
| `backend/infrastructure/state/` | Solo `__init__.py` | State real está en `backend/app/state/` |
| `backend/presentation/http/` | Solo `__init__.py` | HTTP API está en `backend/app/api/` |
| `backend/presentation/websocket/` | Solo `__init__.py` | WebSocket está en `backend/app/api/` |

**Acción:** ✂️ ELIMINAR - son placeholders para una migración que no se completó

### 1.3 Duplicación Cross-Layer

| Archivo Nuevo | Archivo Legacy | Duplica |
|---------------|----------------|---------|
| `backend/infrastructure/ml/config.py` (93 líneas) | `backend/ml/config.py` (180 líneas) | Configuración ML |
| `backend/infrastructure/ml/inference/model_inference.py` (118 líneas) | `backend/ml/model_inference.py` (549 líneas) | Inferencia ML |

**Acción:** ✂️ ELIMINAR los de `backend/infrastructure/ml/` - son wrappers incompletos

---

## 🟡 2. PAQUETES FUSIONABLES

### 2.1 Settings Duplicados

```
backend/app/core/settings.py (116 líneas)     ── FUSIONAR ──→  backend/shared/config/settings.py
backend/shared/config/settings.py (122 líneas)                   (versión unificada)
```

**Diferencia detectada:**
- `app/core/settings.py`: Configuración legacy con `pydantic-settings`
- `shared/config/settings.py`: Nueva configuración Clean Architecture

**Acción:** 🔗 FUSIONAR en `shared/config/settings.py` y actualizar imports en `main.py`

### 2.2 Logging Duplicado

```
backend/app/core/logging.py (27 líneas)       ── FUSIONAR ──→  backend/shared/logging/logger.py
backend/shared/logging/logger.py (29 líneas)                    (versión unificada)
```

**Acción:** 🔗 FUSIONAR en `shared/logging/logger.py`

### 2.3 Entidades Duplicadas

| Entidad | Legacy | Clean Architecture |
|---------|--------|-------------------|
| `Trade` | `app/domain/entities/trade.py` (198 líneas) | `domain/entities/trade.py` (198 líneas) |
| `Signal` | `app/domain/entities/signal.py` (66 líneas) | `domain/entities/signal.py` (66 líneas) |
| `Candle` | `app/domain/entities/candle.py` (34 líneas) | `domain/entities/candle.py` (34 líneas) |
| `Tick` | `app/domain/entities/value_objects/tick.py` (26 líneas) | `domain/value_objects/tick.py` (26 líneas) |
| `PerformanceMetrics` | `app/domain/entities/value_objects/performance_metrics.py` (177 líneas) | `domain/value_objects/performance_metrics.py` (177 líneas) |

**Acción:** 🔗 ELIMINAR las de `backend/app/domain/` y usar las de `backend/domain/`

---

## 🟠 3. PAQUETES QUE DEBEN DIVIDIRSE

### 3.1 `backend/app/services/signal_engine.py` (704 líneas)
**Problema:** God Class - mezcla múltiples responsabilidades

**Responsabilidades detectadas:**
1. Evaluación de EMA Cross (líneas 1-150)
2. Evaluación de RSI Reversal (líneas 151-250)
3. Evaluación de S/R Bounce (líneas 251-400)
4. Evaluación de Breakout (líneas 401-500)
5. Multi-confirmación y agregación (líneas 501-600)
6. Gestión de cooldown (líneas 601-704)

**Propuesta de división:**
```
backend/domain/services/
├── signal_evaluators/
│   ├── __init__.py
│   ├── ema_cross_evaluator.py      (~150 líneas)
│   ├── rsi_reversal_evaluator.py   (~100 líneas)
│   ├── sr_bounce_evaluator.py      (~150 líneas)
│   └── breakout_evaluator.py       (~100 líneas)
├── signal_aggregator.py            (~150 líneas) - multi-confirmación
└── signal_cooldown.py              (~100 líneas) - gestión de cooldown
```

### 3.2 `backend/ml/model_trainer.py` (749 líneas)
**Problema:** Mezcla preparación de datos, entrenamiento, y evaluación

**Propuesta de división:**
```
backend/ml/trainer/
├── __init__.py
├── data_preparator.py     (~200 líneas)
├── model_trainer.py       (~300 líneas)
├── model_evaluator.py     (~150 líneas)
└── training_pipeline.py   (~100 líneas) - orquestación
```

### 3.3 `backend/app/infrastructure/repositories/trade_repository.py` (508 líneas)
**Problema:** Repository con lógica de negocio embebida

**Responsabilidades mezcladas:**
- CRUD de trades (correcto)
- Cálculo de estadísticas (❌ debería estar en StatsService)
- Agregaciones complejas (❌ debería estar en QueryService)

**Propuesta:**
```
backend/infrastructure/persistence/repositories/
├── trade_repository.py           (~200 líneas) - solo CRUD
backend/application/services/
├── trade_query_service.py        (~150 líneas) - queries complejas
├── trade_stats_service.py        (~150 líneas) - cálculo de stats
```

---

## 🔵 4. BOUNDED CONTEXTS IMPLÍCITOS DETECTADOS

### 4.1 Mapa de Bounded Contexts

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           QuantPulse Sistema                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐  │
│  │   TRADING CONTEXT    │   │  MARKET DATA CONTEXT │   │    ML CONTEXT        │  │
│  │                      │   │                      │   │                      │  │
│  │ - Signal Generation  │   │ - Tick Processing    │   │ - Model Training     │  │
│  │ - Trade Simulation   │   │ - Candle Building    │   │ - Model Inference    │  │
│  │ - Risk Management    │   │ - Indicator Calc     │   │ - Dataset Building   │  │
│  │ - Trade State        │   │ - S/R Detection      │   │ - Model Registry     │  │
│  │                      │   │ - Timeframe Agg      │   │                      │  │
│  └──────────────────────┘   └──────────────────────┘   └──────────────────────┘  │
│            │                          │                          │               │
│            └──────────────────────────┼──────────────────────────┘               │
│                                       │                                          │
│  ┌──────────────────────┐   ┌────────┴─────────────┐                            │
│  │  ANALYTICS CONTEXT   │   │  SHARED KERNEL       │                            │
│  │                      │   │                      │                            │
│  │ - Performance Stats  │   │ - Settings           │                            │
│  │ - Metrics Calc       │   │ - Logging            │                            │
│  │ - Trade History      │   │ - Domain Events      │                            │
│  │                      │   │ - Base Entities      │                            │
│  └──────────────────────┘   └──────────────────────┘                            │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Archivos por Bounded Context

#### Trading Context (`backend/trading/`)
- `signal_engine.py` → `trading/services/signal_generator.py`
- `trade_simulator.py` → `trading/services/trade_simulator.py`
- `trade_state.py` → `trading/state/trade_state.py`
- `risk_calculator.py` → `trading/domain/risk_calculator.py`

#### Market Data Context (`backend/market_data/`)
- `candle_builder.py` → `market_data/services/candle_builder.py`
- `indicator_service.py` → `market_data/services/indicator_service.py`
- `support_resistance_service.py` → `market_data/services/sr_service.py`
- `timeframe_aggregator.py` → `market_data/services/tf_aggregator.py`
- `market_state.py` → `market_data/state/market_state.py`
- `indicator_state.py` → `market_data/state/indicator_state.py`

#### ML Context (`backend/ml/`) - YA BIEN DEFINIDO ✅
- `model_trainer.py`
- `model_inference.py`
- `model_registry.py`
- `dataset_builder.py`

#### Analytics Context (`backend/analytics/`)
- `stats_engine.py` → `analytics/services/stats_engine.py`
- `performance_metrics.py` → `analytics/domain/performance_metrics.py`

---

## 🟣 5. VIOLACIONES ARQUITECTÓNICAS DETECTADAS

### 5.1 Dominio Impuro

| Archivo | Violación | Impacto |
|---------|-----------|---------|
| `backend/app/services/signal_engine.py` | Importa `datetime`, `asyncio`, `numpy` | Alto - lógica de dominio contaminada |
| `backend/app/services/stats_engine.py` | Importa `numpy`, `scipy` | Medio - cálculos estadísticos miliares |
| `backend/app/domain/entities/trade.py` | Usa `decimal.Decimal` directamente | Bajo - aceptable para finanzas |

### 5.2 Capa Application Orquestando Mal

**Archivo:** `backend/app/application/process_tick_usecase.py` (218 líneas)

**Problema:** Contiene lógica de negocio compleja en lugar de solo orquestar:
```python
# Líneas 150-180: Cálculo de indicadores (debería estar en domain service)
# Líneas 181-200: Evaluación de señales (debería estar en domain service)
```

### 5.3 Infrastructure Mezclada con Dominio

**Archivo:** `backend/app/infrastructure/repositories/trade_repository.py`

**Problema:** Contiene métodos como `calculate_win_rate()`, `get_performance_summary()` que son lógica de dominio, no persistencia.

### 5.4 Container No Usado

**Archivo:** `backend/container.py` (289 líneas)

**Problema:** Nunca es importado por `main.py`. Toda la DI se hace manualmente en main.py.

---

## 🟢 6. NUEVA ESTRUCTURA PROPUESTA

```
backend/
├── main.py                          # Entry point (mantener, refactorizar imports)
├── container.py                     # DI Container (conectar a main.py)
│
├── shared/                          # Shared Kernel (mantener)
│   ├── config/
│   │   └── settings.py              # Settings unificado
│   ├── logging/
│   │   └── logger.py                # Logging unificado
│   └── exceptions/
│       └── base_exceptions.py       # Excepciones base
│
├── trading/                         # 🆕 Trading Bounded Context
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── signal.py
│   │   │   └── trade.py
│   │   ├── value_objects/
│   │   │   └── trade_result.py
│   │   ├── services/
│   │   │   ├── signal_rules.py
│   │   │   └── risk_calculator.py
│   │   └── repositories/
│   │       ├── signal_repository.py     # Interface
│   │       └── trade_repository.py      # Interface
│   ├── application/
│   │   ├── use_cases/
│   │   │   ├── generate_signal_usecase.py
│   │   │   └── simulate_trade_usecase.py
│   │   └── dto/
│   │       ├── signal_dto.py
│   │       └── trade_dto.py
│   ├── infrastructure/
│   │   └── repositories/
│   │       ├── signal_repository_impl.py
│   │       └── trade_repository_impl.py
│   └── state/
│       └── trade_state.py
│
├── market_data/                     # 🆕 Market Data Bounded Context
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── candle.py
│   │   │   └── tick.py
│   │   └── services/
│   │       ├── indicator_calculator.py
│   │       └── sr_detector.py
│   ├── application/
│   │   └── use_cases/
│   │       └── process_tick_usecase.py
│   ├── infrastructure/
│   │   ├── deriv_client.py
│   │   └── event_bus.py
│   ├── services/
│   │   ├── candle_builder.py
│   │   ├── indicator_service.py
│   │   ├── sr_service.py
│   │   └── tf_aggregator.py
│   └── state/
│       ├── market_state.py
│       └── indicator_state.py
│
├── analytics/                       # 🆕 Analytics Bounded Context
│   ├── domain/
│   │   ├── entities/
│   │   │   └── performance_metrics.py
│   │   └── services/
│   │       └── metrics_calculator.py
│   ├── application/
│   │   └── use_cases/
│   │       └── calculate_stats_usecase.py
│   └── services/
│       └── stats_engine.py
│
├── ml/                              # ML Bounded Context (mantener, bien estructurado)
│   ├── config.py
│   ├── model_trainer.py
│   ├── model_inference.py
│   ├── model_registry.py
│   ├── dataset_builder.py
│   └── train.py
│
├── presentation/                    # 🆕 Presentation Layer (API + WebSocket)
│   ├── api/
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── dependencies.py
│   └── websocket/
│       └── websocket_manager.py
│
├── persistence/                     # 🆕 Shared Persistence (DB, Models, Migrations)
│   ├── database.py
│   ├── models/
│   │   ├── signal_model.py
│   │   ├── trade_model.py
│   │   └── performance_model.py
│   └── migrations/                  # (mover de db/)
│
└── 🗑️ ELIMINAR:
    ├── app/                         # Todo el directorio legacy
    ├── domain/                      # Migrar a bounded contexts
    ├── application/                 # Migrar a bounded contexts
    └── infrastructure/              # Migrar a bounded contexts/persistence
```

---

## 📋 7. PLAN DE MIGRACIÓN (Fases)

### Fase 1: Limpieza Inmediata (1-2 horas)
```bash
# Eliminar dead code
rm backend/app/application/generate_signal_usecase.py
rm backend/app/application/simulate_trade_usecase.py
rm backend/app/application/stats_usecase.py
rm backend/app/services/pattern_detector.py

# Eliminar directorios vacíos
rm -r backend/infrastructure/external/deriv/
rm -r backend/infrastructure/external/messaging/
rm -r backend/infrastructure/ml/training/
rm -r backend/infrastructure/ml/registry/
rm -r backend/infrastructure/state/
rm -r backend/presentation/http/
rm -r backend/presentation/websocket/

# Eliminar duplicados ML
rm -r backend/infrastructure/ml/
```

### Fase 2: Conectar Container (2-4 horas)
1. Modificar `main.py` para usar `container.py`
2. Actualizar imports de servicios
3. Validar que la aplicación sigue funcionando

### Fase 3: Fusionar Duplicados (4-8 horas)
1. Unificar `settings.py` → `shared/config/settings.py`
2. Unificar `logging.py` → `shared/logging/logger.py`
3. Eliminar entidades duplicadas en `app/domain/`
4. Actualizar todos los imports

### Fase 4: Crear Bounded Contexts (1-2 días)
1. Crear estructura de carpetas para `trading/`, `market_data/`, `analytics/`
2. Mover archivos gradualmente
3. Actualizar imports
4. Ejecutar tests después de cada movimiento

### Fase 5: Eliminar Legacy (1 día)
1. Verificar que todo está migrado
2. Ejecutar tests completos
3. Eliminar `backend/app/`
4. Commit final

---

## 📈 8. MAPA DE DEPENDENCIAS IDEAL

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              main.py + container.py                          │
│                                     │                                        │
│                    ┌────────────────┼────────────────┐                      │
│                    ▼                ▼                ▼                      │
│             ┌──────────┐     ┌──────────┐     ┌──────────┐                 │
│             │  trading │     │market_data│    │ analytics│                 │
│             └────┬─────┘     └─────┬────┘     └────┬─────┘                 │
│                  │                 │               │                        │
│                  └────────┬────────┴───────────────┘                        │
│                           ▼                                                  │
│                    ┌──────────┐                                             │
│                    │   ml/    │ ◄── Puede ser llamado por trading           │
│                    └────┬─────┘                                             │
│                         │                                                    │
│            ┌────────────┼────────────┐                                      │
│            ▼            ▼            ▼                                      │
│     ┌──────────┐ ┌──────────┐ ┌──────────┐                                 │
│     │ shared/  │ │persistence│ │presentation│                              │
│     │ config   │ │  models   │ │    api     │                              │
│     │ logging  │ │ database  │ │ websocket  │                              │
│     └──────────┘ └──────────┘ └──────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Reglas de Dependencia:
━━━━━━━━━━━━━━━━━━━━━
✅ domain/ → (nada externo, solo shared/exceptions)
✅ application/ → domain/, ports (interfaces)
✅ infrastructure/ → application/ports, domain/entities
✅ presentation/ → application/use_cases, application/dto
✅ main.py → container → todos los módulos
❌ domain/ NO puede importar infrastructure/
❌ application/ NO puede importar FastAPI, SQLAlchemy, etc.
❌ Bounded Context A NO puede importar de Bounded Context B directamente
   (usar eventos de dominio o Shared Kernel)
```

---

## ✅ 9. CHECKLIST DE VALIDACIÓN POST-MIGRACIÓN

### Validaciones Arquitectónicas

- [ ] `backend/trading/domain/` NO importa `fastapi`, `sqlalchemy`, `asyncio`
- [ ] `backend/market_data/domain/` NO importa `websockets`, `httpx`
- [ ] `backend/*/application/` solo importa `domain/` y `ports/`
- [ ] `backend/*/application/use_cases/` solo orquestan, no calculan
- [ ] `backend/persistence/` NO tiene lógica de negocio
- [ ] `backend/presentation/` NO tiene lógica de negocio
- [ ] `container.py` es el ÚNICO lugar que crea dependencias concretas
- [ ] Tests pasan con mocks inyectados vía `create_test_container()`

### Métricas de Calidad

| Métrica | Antes | Objetivo |
|---------|-------|----------|
| Líneas de código total | ~12,700 | ~10,000 (reducción 20%) |
| Archivos vacíos/stubs | 15+ | 0 |
| Duplicación de código | ~1,500 líneas | <100 líneas |
| Bounded Contexts claros | 0 | 4 (Trading, MarketData, Analytics, ML) |
| Container conectado | No | Sí |

---

## 📝 10. CONCLUSIONES

### Hallazgos Principales

1. **Arquitectura Dual No Integrada**: El sistema más crítico. La nueva arquitectura Clean fue creada pero nunca conectada.

2. **Dead Code Significativo**: 15+ archivos/directorios que solo ocupan espacio y confunden.

3. **God Classes**: `signal_engine.py` (704 líneas) y `model_trainer.py` (749 líneas) necesitan ser divididos.

4. **Bounded Contexts Implícitos**: La separación Trading/MarketData/Analytics existe conceptualmente pero no en la estructura de carpetas.

5. **Violaciones Clean Architecture**: Lógica de dominio en repositorios, application con cálculos, etc.

### Recomendación Final

**Prioridad CRÍTICA:** Conectar `container.py` a `main.py` antes de cualquier otra refactorización. Sin esto, todo el trabajo de Clean Architecture es código muerto.

**Esfuerzo estimado total:** 3-5 días de trabajo enfocado para completar las 5 fases de migración.

---

*Fin del Informe de Auditoría Arquitectónica*
