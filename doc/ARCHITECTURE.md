# QuantPulse – Clean Architecture Refactoring

## 📋 Propuesta de Reestructuración

**Versión:** 2.0  
**Fecha:** 2026-02-27  
**Estado:** En implementación

---

## 1. Estructura Actual vs Nueva

### Estructura Actual (Problemática)
```
backend/app/
├── api/              # Mezcla HTTP + WebSocket
├── application/      # Use cases sin ports
├── domain/           # Solo entities, falta todo lo demás
├── infrastructure/   # Repos + DB + External
├── services/         # PROBLEMA: Mezcla dominio + infra
├── state/            # PROBLEMA: ¿Infra o dominio?
├── core/             # Config + Logging
backend/ml/           # PROBLEMA: No es bounded context claro
backend/db/           # Migraciones
```

### Estructura Nueva (Clean Architecture)
```
backend/
├── domain/                      ← NÚCLEO PURO (capa 0)
│   ├── entities/                # Entidades de negocio
│   ├── value_objects/           # Objetos inmutables
│   ├── services/                # Domain services puros
│   ├── repositories/            # Interfaces (ABCs)
│   ├── events/                  # Domain events
│   └── exceptions/              # Excepciones de dominio
│
├── application/                 ← CASOS DE USO (capa 1)
│   ├── use_cases/               # Orquestación de dominio
│   ├── dto/                     # Data Transfer Objects
│   ├── ports/                   # Interfaces hacia infra
│   └── services/                # Application services
│
├── infrastructure/              ← IMPLEMENTACIONES (capa 2)
│   ├── persistence/             # Base de datos
│   │   ├── database.py          # Engine + Session
│   │   ├── models/              # SQLAlchemy models
│   │   ├── mappers/             # Model ↔ Entity
│   │   └── repositories/        # Impl concretas
│   ├── external/                # APIs externas
│   │   ├── deriv/               # Deriv WebSocket
│   │   └── messaging/           # Event bus
│   ├── state/                   # Estado en memoria
│   └── ml/                      # ML Bounded Context
│       ├── training/
│       ├── inference/
│       └── registry/
│
├── presentation/                ← API (capa 3)
│   ├── http/                    # FastAPI routes
│   └── websocket/               # WebSocket handlers
│
├── shared/                      ← TRANSVERSAL
│   ├── config/                  # Settings
│   ├── logging/                 # Logging setup
│   └── utils/                   # Helpers comunes
│
├── container.py                 # Dependency Injection
└── main.py                      # Entry point
```

---

## 2. Reglas de Dependencia (Dependency Rule)

```
┌─────────────────────────────────────────────────────────────┐
│                      presentation                           │
│  (Solo llama a use_cases, NUNCA a domain directamente)     │
└────────────────────────────┬────────────────────────────────┘
                             │ depends on
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      application                            │
│  (Use cases + Ports, depende de domain + interfaces)       │
└────────────────────────────┬────────────────────────────────┘
                             │ depends on
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                        domain                               │
│  (CERO dependencias externas, lógica pura de negocio)      │
└─────────────────────────────────────────────────────────────┘
                             ▲
                             │ implements
┌─────────────────────────────────────────────────────────────┐
│                    infrastructure                           │
│  (Implementa interfaces de domain/application)             │
└─────────────────────────────────────────────────────────────┘
```

### ✅ Dependencias Permitidas
- `domain` → (nada, excepto stdlib)
- `application` → `domain`, ports (interfaces propias)
- `infrastructure` → `domain`, `application` (para implementar)
- `presentation` → `application` (use cases)
- `shared` → (nada, usado por todos)

### ❌ Dependencias Prohibidas
- `domain` → `infrastructure` ❌
- `domain` → `application` ❌
- `domain` → `presentation` ❌
- `domain` → frameworks externos ❌
- `application` → `infrastructure` concreta ❌

---

## 3. Mapeo de Archivos: Dónde Mover Cada Cosa

### 3.1 domain/ (Lógica Pura)

| Origen | Destino | Razón |
|--------|---------|-------|
| `app/domain/entities/*.py` | `domain/entities/` | Ya está correcto |
| `app/domain/entities/value_objects/*.py` | `domain/value_objects/` | Promover a nivel superior |
| `app/services/signal_engine.py` (lógica) | `domain/services/signal_rules.py` | Extraer reglas puras |
| Nuevo | `domain/repositories/*_interface.py` | ABCs para repos |
| Nuevo | `domain/exceptions/` | DomainError, etc. |

### 3.2 application/ (Casos de Uso)

| Origen | Destino | Razón |
|--------|---------|-------|
| `app/application/*.py` | `application/use_cases/` | Renombrar carpeta |
| Nuevo | `application/ports/*.py` | Interfaces a infra |
| Nuevo | `application/dto/*.py` | Request/Response DTOs |

### 3.3 infrastructure/ (Implementaciones)

| Origen | Destino | Razón |
|--------|---------|-------|
| `app/infrastructure/database.py` | `infrastructure/persistence/database.py` | Subcarpeta persistence |
| `app/infrastructure/models/*.py` | `infrastructure/persistence/models/` | Subcarpeta models |
| `app/infrastructure/repositories/*.py` | `infrastructure/persistence/repositories/` | Impl de repos |
| Nuevo | `infrastructure/persistence/mappers/` | Entity ↔ Model |
| `app/infrastructure/deriv_client.py` | `infrastructure/external/deriv/client.py` | Subcarpeta external |
| `app/infrastructure/event_bus.py` | `infrastructure/external/messaging/event_bus.py` | Messaging |
| `app/state/*.py` | `infrastructure/state/` | Estado = infra |
| `ml/*.py` | `infrastructure/ml/` + subdirs | ML bounded context |

### 3.4 presentation/ (API)

| Origen | Destino | Razón |
|--------|---------|-------|
| `app/api/routes.py` | `presentation/http/routes.py` | HTTP separado |
| `app/api/shemas.py` | `presentation/http/schemas.py` | Fix typo también |
| `app/api/websocket_manager.py` | `presentation/websocket/manager.py` | WS separado |

### 3.5 shared/ (Utilidades)

| Origen | Destino | Razón |
|--------|---------|-------|
| `app/core/settings.py` | `shared/config/settings.py` | Config global |
| `app/core/logging.py` | `shared/logging/logger.py` | Logging global |
| `app/core/config.py` | `shared/config/` | Merge con settings |

---

## 4. Ejemplos de Código

### 4.1 Repository Interface (domain)

```python
# domain/repositories/signal_repository.py
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.entities.signal import Signal

class ISignalRepository(ABC):
    """Interfaz abstracta para persistencia de señales."""
    
    @abstractmethod
    async def save(self, signal: Signal, symbol_id: int) -> str:
        """Persiste una señal. Retorna UUID."""
        pass
    
    @abstractmethod
    async def find_by_id(self, uuid: str) -> Optional[Signal]:
        """Busca señal por UUID."""
        pass
    
    @abstractmethod
    async def find_by_symbol(
        self, 
        symbol: str, 
        limit: int = 50
    ) -> List[Signal]:
        """Busca señales por símbolo."""
        pass
```

### 4.2 Repository Implementation (infrastructure)

```python
# infrastructure/persistence/repositories/signal_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from domain.repositories.signal_repository import ISignalRepository
from domain.entities.signal import Signal
from infrastructure.persistence.models.signal import SignalModel
from infrastructure.persistence.mappers.signal_mapper import SignalMapper

class MySQLSignalRepository(ISignalRepository):
    """Implementación MySQL del repositorio de señales."""
    
    def __init__(self, session: AsyncSession):
        self._session = session
        self._mapper = SignalMapper()
    
    async def save(self, signal: Signal, symbol_id: int) -> str:
        model = self._mapper.to_model(signal, symbol_id)
        self._session.add(model)
        await self._session.flush()
        return signal.id
    
    async def find_by_id(self, uuid: str) -> Optional[Signal]:
        result = await self._session.execute(
            select(SignalModel).where(SignalModel.uuid == uuid)
        )
        model = result.scalar_one_or_none()
        return self._mapper.to_entity(model) if model else None
```

### 4.3 Use Case (application)

```python
# application/use_cases/generate_signal_usecase.py
from dataclasses import dataclass
from typing import Optional
from domain.entities.signal import Signal
from domain.repositories.signal_repository import ISignalRepository
from application.ports.event_publisher import IEventPublisher
from application.dto.signal_dto import SignalResponseDTO

@dataclass
class GenerateSignalUseCase:
    """Genera y persiste señales de trading."""
    
    signal_repository: ISignalRepository
    event_publisher: IEventPublisher
    
    async def execute(
        self, 
        signal: Signal, 
        symbol_id: int,
        persist: bool = True
    ) -> SignalResponseDTO:
        """
        Persiste señal y publica evento.
        
        Args:
            signal: Señal generada por domain service
            symbol_id: ID del símbolo
            persist: Si guardar en BD
            
        Returns:
            DTO con datos de la señal
        """
        if persist:
            await self.signal_repository.save(signal, symbol_id)
        
        # Publicar evento para WebSocket
        await self.event_publisher.publish(
            topic="signal",
            data=signal.to_dict()
        )
        
        return SignalResponseDTO.from_entity(signal)
```

### 4.4 Dependency Injection Container

```python
# container.py
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

# Domain interfaces
from domain.repositories.signal_repository import ISignalRepository
from domain.repositories.trade_repository import ITradeRepository

# Infrastructure implementations
from infrastructure.persistence.repositories.signal_repository import MySQLSignalRepository
from infrastructure.persistence.repositories.trade_repository import MySQLTradeRepository
from infrastructure.external.messaging.event_bus import EventBus
from infrastructure.state.market_state import MarketStateManager

# Application use cases
from application.use_cases.process_tick_usecase import ProcessTickUseCase
from application.use_cases.generate_signal_usecase import GenerateSignalUseCase

@dataclass
class Container:
    """
    Contenedor de Dependency Injection.
    
    Resuelve dependencias en tiempo de arranque.
    Inyecta implementaciones concretas donde se esperan interfaces.
    """
    
    # Infra singletons
    event_bus: EventBus
    market_state: MarketStateManager
    
    # Session factory para repos
    _session_factory: callable
    
    def get_signal_repository(self, session: AsyncSession) -> ISignalRepository:
        """Factory method para repo de señales."""
        return MySQLSignalRepository(session)
    
    def get_trade_repository(self, session: AsyncSession) -> ITradeRepository:
        """Factory method para repo de trades."""
        return MySQLTradeRepository(session)
    
    def get_process_tick_usecase(self) -> ProcessTickUseCase:
        """Construye ProcessTickUseCase con todas sus dependencias."""
        return ProcessTickUseCase(
            event_bus=self.event_bus,
            market_state=self.market_state,
            # ... demás dependencias
        )

# Singleton global
_container: Container | None = None

def get_container() -> Container:
    """Obtiene el contenedor global."""
    if _container is None:
        raise RuntimeError("Container not initialized. Call init_container() first.")
    return _container

def init_container(session_factory: callable) -> Container:
    """Inicializa el contenedor con las dependencias."""
    global _container
    _container = Container(
        event_bus=EventBus(),
        market_state=MarketStateManager(),
        _session_factory=session_factory,
    )
    return _container
```

---

## 5. Beneficios de la Reestructuración

### 5.1 Testabilidad
- **Antes:** Tests necesitan DB real, Deriv connection, etc.
- **Después:** Domain tests con mocks puros, 0 dependencias externas.

```python
# test_signal_rules.py (domain puro)
def test_ema_cross_bullish():
    rules = SignalRules()
    result = rules.check_ema_cross(
        prev_ema_fast=100, prev_ema_slow=101,
        curr_ema_fast=101, curr_ema_slow=100
    )
    assert result == "ema_cross_bullish"
```

### 5.2 Escalabilidad
- ML como bounded context puede ser microservicio.
- Fácil agregar nuevos repos (PostgreSQL, MongoDB).
- Use cases agnósticos a la presentación (CLI, REST, GraphQL).

### 5.3 Mantenibilidad
- Cada capa tiene responsabilidad única.
- Cambios en infra no afectan dominio.
- Nuevos developers onboarding más rápido.

---

## 6. Plan de Migración (Sin Romper)

### Fase 1: Estructura Paralela
1. Crear nuevas carpetas vacías
2. Crear interfaces en domain/repositories/
3. Crear ports en application/ports/

### Fase 2: Mover Gradualmente
1. Copiar (no mover) archivos críticos
2. Crear compatibility imports en ubicaciones antiguas
3. Verificar que sistema sigue funcionando

### Fase 3: Actualizar Imports
1. Buscar/reemplazar imports antiguos
2. Eliminar archivos duplicados
3. Eliminar compatibility imports

### Fase 4: Refinamiento
1. Extraer lógica pura de services/ a domain/services/
2. Crear mappers Entity ↔ Model
3. Implementar Container completo

---

## 7. Estructura Final de Archivos

```
backend/
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── candle.py
│   │   ├── signal.py
│   │   └── trade.py
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── tick.py
│   │   └── performance_metrics.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── signal_rules.py         # Lógica pura de señales
│   │   ├── risk_calculator.py      # Cálculo RR, SL, TP
│   │   └── indicator_calculator.py # EMA, RSI puros
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── signal_repository.py    # Interface
│   │   └── trade_repository.py     # Interface
│   ├── events/
│   │   ├── __init__.py
│   │   └── domain_events.py        # SignalGenerated, TradeClosed
│   └── exceptions/
│       ├── __init__.py
│       └── domain_errors.py
│
├── application/
│   ├── __init__.py
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── process_tick_usecase.py
│   │   ├── generate_signal_usecase.py
│   │   ├── simulate_trade_usecase.py
│   │   └── get_stats_usecase.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── event_publisher.py      # Interface
│   │   ├── market_data_provider.py # Interface
│   │   └── ml_predictor.py         # Interface
│   ├── dto/
│   │   ├── __init__.py
│   │   ├── signal_dto.py
│   │   ├── trade_dto.py
│   │   └── stats_dto.py
│   └── services/
│       ├── __init__.py
│       └── signal_orchestrator.py  # Coordina domain services
│
├── infrastructure/
│   ├── __init__.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── signal.py
│   │   │   ├── trade.py
│   │   │   ├── symbol.py
│   │   │   └── performance.py
│   │   ├── mappers/
│   │   │   ├── __init__.py
│   │   │   ├── signal_mapper.py
│   │   │   └── trade_mapper.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── signal_repository.py  # Implementación
│   │       └── trade_repository.py   # Implementación
│   ├── external/
│   │   ├── __init__.py
│   │   ├── deriv/
│   │   │   ├── __init__.py
│   │   │   └── client.py
│   │   └── messaging/
│   │       ├── __init__.py
│   │       └── event_bus.py
│   ├── state/
│   │   ├── __init__.py
│   │   ├── market_state.py
│   │   ├── indicator_state.py
│   │   └── trade_state.py
│   └── ml/
│       ├── __init__.py
│       ├── config.py
│       ├── training/
│       │   ├── __init__.py
│       │   ├── dataset_builder.py
│       │   └── model_trainer.py
│       ├── inference/
│       │   ├── __init__.py
│       │   └── predictor.py
│       └── registry/
│           ├── __init__.py
│           └── model_registry.py
│
├── presentation/
│   ├── __init__.py
│   ├── http/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── dependencies.py
│   └── websocket/
│       ├── __init__.py
│       └── manager.py
│
├── shared/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── logging/
│   │   ├── __init__.py
│   │   └── logger.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── container.py
├── main.py
└── __init__.py
```

---

## 8. Compatibility Layer

Durante la migración, mantener imports antiguos funcionando:

```python
# backend/app/domain/entities/__init__.py (TEMPORAL)
# Redirect imports to new location
from backend.domain.entities.signal import Signal
from backend.domain.entities.trade import SimulatedTrade, TradeStatus
from backend.domain.entities.candle import Candle

__all__ = ["Signal", "SimulatedTrade", "TradeStatus", "Candle"]
```

Esto permite que código legacy siga funcionando mientras se actualiza.

---

## 9. Checklist de Migración

- [ ] Crear estructura de carpetas
- [ ] Crear __init__.py en todas las carpetas
- [ ] Crear interfaces en domain/repositories/
- [ ] Crear ports en application/ports/
- [ ] Mover entities a domain/
- [ ] Mover value_objects a domain/
- [ ] Crear domain/services/ con lógica pura
- [ ] Mover models a infrastructure/persistence/models/
- [ ] Mover repos a infrastructure/persistence/repositories/
- [ ] Crear mappers
- [ ] Mover state a infrastructure/state/
- [ ] Mover deriv_client a infrastructure/external/deriv/
- [ ] Mover event_bus a infrastructure/external/messaging/
- [ ] Reestructurar ML
- [ ] Mover API a presentation/http/
- [ ] Mover WebSocket a presentation/websocket/
- [ ] Crear shared/ con config y logging
- [ ] Crear container.py
- [ ] Actualizar main.py
- [ ] Actualizar todos los imports
- [ ] Eliminar app/ antigua
- [ ] Tests de integración
