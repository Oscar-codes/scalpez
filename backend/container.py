"""
Dependency Injection Container.

Este módulo proporciona el contenedor de inyección de dependencias
que gestiona todas las instancias de servicios, repositorios y casos de uso.

Clean Architecture: Este contenedor vive en la capa más externa y es el único
lugar donde se crean dependencias concretas.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from functools import lru_cache

# Domain
from backend.domain.repositories.signal_repository import ISignalRepository
from backend.domain.repositories.trade_repository import ITradeRepository
from backend.domain.services.signal_rules import SignalRules
from backend.domain.services.risk_calculator import RiskCalculator
from backend.domain.services.indicator_calculator import IndicatorCalculator

# Application Ports
from backend.application.ports.event_publisher import IEventPublisher
from backend.application.ports.market_data_provider import IMarketDataProvider
from backend.application.ports.ml_predictor import IMLPredictor

# Shared
from backend.shared.config.settings import Settings


@dataclass
class Container:
    """
    Contenedor de Inyección de Dependencias.
    
    Gestiona el ciclo de vida de todas las dependencias de la aplicación.
    Sigue el principio de inversión de dependencias: las capas internas
    dependen de abstracciones, no de implementaciones concretas.
    """
    
    # Configuración
    settings: Settings = field(default_factory=Settings)
    
    # Repositorios (implementaciones concretas)
    _signal_repository: Optional[ISignalRepository] = None
    _trade_repository: Optional[ITradeRepository] = None
    
    # Ports (implementaciones concretas)
    _event_publisher: Optional[IEventPublisher] = None
    _market_data_provider: Optional[IMarketDataProvider] = None
    _ml_predictor: Optional[IMLPredictor] = None
    
    # Domain Services (stateless, se pueden compartir)
    _signal_rules: Optional[SignalRules] = None
    _risk_calculator: Optional[RiskCalculator] = None
    _indicator_calculator: Optional[IndicatorCalculator] = None
    
    # Cache de instancias
    _instances: Dict[str, Any] = field(default_factory=dict)
    
    # ==================== Domain Services ====================
    
    @property
    def signal_rules(self) -> SignalRules:
        """Obtiene o crea SignalRules (singleton)."""
        if self._signal_rules is None:
            self._signal_rules = SignalRules()
        return self._signal_rules
    
    @property
    def risk_calculator(self) -> RiskCalculator:
        """Obtiene o crea RiskCalculator (singleton)."""
        if self._risk_calculator is None:
            self._risk_calculator = RiskCalculator()
        return self._risk_calculator
    
    @property
    def indicator_calculator(self) -> IndicatorCalculator:
        """Obtiene o crea IndicatorCalculator (singleton)."""
        if self._indicator_calculator is None:
            self._indicator_calculator = IndicatorCalculator()
        return self._indicator_calculator
    
    # ==================== Repositories ====================
    
    @property
    def signal_repository(self) -> ISignalRepository:
        """Obtiene el repositorio de señales."""
        if self._signal_repository is None:
            # Import aquí para evitar dependencia circular
            from backend.infrastructure.persistence.repositories.signal_repository_impl import SignalRepositoryImpl
            from backend.infrastructure.persistence.database import get_session
            self._signal_repository = SignalRepositoryImpl(get_session())
        return self._signal_repository
    
    @property
    def trade_repository(self) -> ITradeRepository:
        """Obtiene el repositorio de trades."""
        if self._trade_repository is None:
            from backend.infrastructure.persistence.repositories.trade_repository_impl import TradeRepositoryImpl
            from backend.infrastructure.persistence.database import get_session
            self._trade_repository = TradeRepositoryImpl(get_session())
        return self._trade_repository
    
    # ==================== Ports ====================
    
    @property
    def event_publisher(self) -> IEventPublisher:
        """Obtiene el publicador de eventos."""
        if self._event_publisher is None:
            from backend.infrastructure.external.event_bus_adapter import EventBusAdapter
            self._event_publisher = EventBusAdapter()
        return self._event_publisher
    
    @property
    def market_data_provider(self) -> IMarketDataProvider:
        """Obtiene el proveedor de datos de mercado."""
        if self._market_data_provider is None:
            from backend.infrastructure.external.deriv_adapter import DerivAdapter
            self._market_data_provider = DerivAdapter(self.settings)
        return self._market_data_provider
    
    @property
    def ml_predictor(self) -> Optional[IMLPredictor]:
        """Obtiene el predictor ML si está habilitado."""
        if not self.settings.ml_enabled:
            return None
        if self._ml_predictor is None:
            from backend.infrastructure.ml.inference.model_inference import ModelInference
            self._ml_predictor = ModelInference(self.settings)
        return self._ml_predictor
    
    # ==================== Use Cases ====================
    
    def get_generate_signal_usecase(self):
        """
        Factory para GenerateSignalUseCase.
        
        Cada llamada crea una nueva instancia para evitar estado compartido.
        """
        from backend.application.use_cases.generate_signal_usecase import GenerateSignalUseCase
        return GenerateSignalUseCase(
            signal_repository=self.signal_repository,
            event_publisher=self.event_publisher,
            signal_rules=self.signal_rules,
            risk_calculator=self.risk_calculator,
            ml_predictor=self.ml_predictor
        )
    
    def get_process_tick_usecase(self):
        """Factory para ProcessTickUseCase."""
        from backend.application.use_cases.process_tick_usecase import ProcessTickUseCase
        return ProcessTickUseCase(
            indicator_calculator=self.indicator_calculator,
            event_publisher=self.event_publisher
        )
    
    def get_simulate_trade_usecase(self):
        """Factory para SimulateTradeUseCase."""
        from backend.application.use_cases.simulate_trade_usecase import SimulateTradeUseCase
        return SimulateTradeUseCase(
            trade_repository=self.trade_repository,
            event_publisher=self.event_publisher,
            risk_calculator=self.risk_calculator
        )
    
    def get_stats_usecase(self):
        """Factory para StatsUseCase."""
        from backend.application.use_cases.stats_usecase import StatsUseCase
        return StatsUseCase(
            trade_repository=self.trade_repository,
            signal_repository=self.signal_repository
        )
    
    # ==================== Lifecycle ====================
    
    def reset(self) -> None:
        """Resetea todas las instancias (útil para tests)."""
        self._signal_repository = None
        self._trade_repository = None
        self._event_publisher = None
        self._market_data_provider = None
        self._ml_predictor = None
        self._signal_rules = None
        self._risk_calculator = None
        self._indicator_calculator = None
        self._instances.clear()
    
    def override(self, name: str, instance: Any) -> None:
        """
        Override una dependencia (útil para tests con mocks).
        
        Args:
            name: Nombre de la dependencia (ej: 'signal_repository')
            instance: Instancia mock a usar
        """
        attr_name = f"_{name}"
        if hasattr(self, attr_name):
            setattr(self, attr_name, instance)
        else:
            raise ValueError(f"Unknown dependency: {name}")


# ==================== Global Container ====================

_container: Optional[Container] = None


def get_container() -> Container:
    """
    Obtiene la instancia global del contenedor.
    
    Patrón Singleton para asegurar una única instancia
    compartida en toda la aplicación.
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container() -> None:
    """
    Resetea el contenedor global.
    
    Útil para tests o reinicialización.
    """
    global _container
    if _container is not None:
        _container.reset()
    _container = None


def init_container(settings: Optional[Settings] = None) -> Container:
    """
    Inicializa el contenedor con configuración específica.
    
    Args:
        settings: Configuración opcional. Si es None, usa valores por defecto.
    
    Returns:
        Container inicializado
    """
    global _container
    if settings is None:
        settings = Settings()
    _container = Container(settings=settings)
    return _container


# ==================== Testing Utilities ====================

class TestContainer(Container):
    """
    Contenedor especializado para tests.
    
    Permite inyectar mocks fácilmente sin modificar
    el contenedor de producción.
    """
    
    def __init__(self, **mocks):
        """
        Inicializa con mocks opcionales.
        
        Args:
            **mocks: Mocks a inyectar (ej: signal_repository=mock_repo)
        """
        super().__init__()
        for name, mock in mocks.items():
            self.override(name, mock)
    
    @classmethod
    def with_mocks(cls, **mocks) -> "TestContainer":
        """Factory method para crear contenedor con mocks."""
        return cls(**mocks)


def create_test_container(**mocks) -> TestContainer:
    """
    Crea un contenedor de pruebas con mocks inyectados.
    
    Ejemplo:
        container = create_test_container(
            signal_repository=mock_signal_repo,
            event_publisher=mock_publisher
        )
    """
    return TestContainer.with_mocks(**mocks)
