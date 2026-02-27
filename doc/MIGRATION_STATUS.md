# Migración a Clean Architecture - Estado

## Resumen
Este documento rastrea el estado de la migración de QuantPulse a Clean Architecture.

## Estado Actual: FASE 1 COMPLETADA (Estructura Paralela)

### ✅ Completado

#### Capa Domain (`backend/domain/`)
- [x] `entities/` - Entidades de dominio (Signal, Trade, Candle)
- [x] `value_objects/` - Objetos de valor (Tick, PerformanceMetrics)
- [x] `services/` - Servicios de dominio puros:
  - SignalRules - Reglas de generación de señales
  - RiskCalculator - Cálculo de SL/TP/RR
  - IndicatorCalculator - Cálculo de indicadores técnicos
- [x] `repositories/` - Interfaces abstractas (ABCs)
- [x] `events/` - Domain Events
- [x] `exceptions/` - Excepciones de dominio

#### Capa Application (`backend/application/`)
- [x] `use_cases/` - Casos de uso orquestadores:
  - GenerateSignalUseCase
  - ProcessTickUseCase
- [x] `ports/` - Interfaces hacia infraestructura:
  - IEventPublisher
  - IMarketDataProvider
  - IMLPredictor
- [x] `dto/` - Data Transfer Objects

#### Capa Infrastructure (`backend/infrastructure/`)
- [x] `persistence/` - Persistencia MySQL:
  - database.py - DatabaseManager
  - models/ - Re-export de modelos ORM
  - repositories/ - SignalRepositoryImpl, TradeRepositoryImpl
  - mappers/ - Entity ↔ Model mappers
- [x] `external/` - Sistemas externos:
  - EventBusAdapter - Implementa IEventPublisher
  - DerivAdapter - Implementa IMarketDataProvider
- [x] `ml/` - Bounded context de Machine Learning

#### Capa Presentation (`backend/presentation/`)
- [x] Estructura creada (http/, websocket/)
- [ ] Migrar routes.py

#### Shared (`backend/shared/`)
- [x] `config/` - Settings centralizados
- [x] `logging/` - Logging centralizado

#### Dependency Injection
- [x] `container.py` - Container de DI completo

### 🔄 Pendiente

#### Fase 2: Migración de Use Cases
- [ ] Migrar ProcessTickUseCase completo a nueva arquitectura
- [ ] Migrar lógica de SignalEngine a GenerateSignalUseCase
- [ ] Migrar TradeSimulator a SimulateTradeUseCase

#### Fase 3: Migración de Presentation
- [ ] Migrar routes.py a presentation/http/
- [ ] Migrar websocket_manager.py a presentation/websocket/
- [ ] Crear controllers/handlers

#### Fase 4: Actualizar Main.py
- [ ] Usar Container para DI
- [ ] Importar desde nuevas ubicaciones
- [ ] Deprecar app/ cuando esté completo

## Cómo Usar la Nueva Arquitectura

### Importaciones
```python
# Domain entities
from backend.domain import Signal, Trade, Candle

# Domain services
from backend.domain.services import SignalRules, RiskCalculator

# Use cases
from backend.application import GenerateSignalUseCase

# DI Container
from backend.container import get_container
```

### Dependency Injection
```python
from backend.container import get_container

container = get_container()

# Obtener use case con todas las dependencias inyectadas
use_case = container.get_generate_signal_usecase()

# Para tests: crear container con mocks
from backend.container import create_test_container

test_container = create_test_container(
    signal_repository=mock_repo,
    event_publisher=mock_publisher,
)
```

## Compatibilidad

El código en `backend/app/` sigue funcionando igual que antes.
La nueva estructura en `backend/domain/`, `backend/application/`, etc.
es paralela y se puede usar gradualmente.

## Próximos Pasos
1. Comenzar a usar nuevos domain services en lugares específicos
2. Migrar tests para usar TestContainer con mocks
3. Gradualmente mover lógica de services/ a domain/services/
4. Cuando esté estable, deprecar app/ y mover todo a la nueva estructura
