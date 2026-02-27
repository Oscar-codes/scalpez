"""
Dependency Injection Container.

Este módulo proporciona el contenedor de inyección de dependencias
que gestiona todas las instancias de servicios, repositorios y casos de uso.

Clean Architecture: Este contenedor vive en la capa más externa y es el único
lugar donde se crean dependencias concretas.

NOTA: Incluye servicios legacy (backend.app) para transición gradual.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING
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

# Legacy imports (para transición)
if TYPE_CHECKING:
    from backend.app.infrastructure.event_bus import EventBus
    from backend.app.state.market_state import MarketStateManager
    from backend.app.state.indicator_state import IndicatorStateManager
    from backend.app.state.trade_state import TradeStateManager
    from backend.app.services.candle_builder import CandleBuilder
    from backend.app.services.indicator_service import IndicatorService
    from backend.app.services.support_resistance_service import SupportResistanceService
    from backend.app.services.signal_engine import SignalEngine
    from backend.app.services.trade_simulator import TradeSimulator
    from backend.app.services.stats_engine import StatsEngine
    from backend.app.services.timeframe_aggregator import TimeframeAggregator
    from backend.app.infrastructure.deriv_client import DerivClient
    from backend.app.application.process_tick_usecase import ProcessTickUseCase as LegacyProcessTickUseCase
    from backend.app.api.websocket_manager import WebSocketManager


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
    
    # ==================== Legacy Services (transición) ====================
    # Estos servicios son de backend.app y se irán migrando gradualmente
    _event_bus: Optional[Any] = None
    _market_state: Optional[Any] = None
    _indicator_state: Optional[Any] = None
    _trade_state: Optional[Any] = None
    _candle_builder: Optional[Any] = None
    _indicator_service: Optional[Any] = None
    _sr_service: Optional[Any] = None
    _signal_engine: Optional[Any] = None
    _trade_simulator: Optional[Any] = None
    _stats_engine: Optional[Any] = None
    _tf_aggregator: Optional[Any] = None
    _deriv_client: Optional[Any] = None
    _legacy_process_tick: Optional[Any] = None
    _ws_manager: Optional[Any] = None
    
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
            from backend.ml.model_inference import ModelInference
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
    
    # ==================== Legacy Services (transición) ====================
    # Estos servicios son de backend.app y se irán migrando a bounded contexts
    
    @property
    def legacy_settings(self):
        """Settings legacy de backend.app.core."""
        from backend.app.core.settings import settings
        return settings
    
    @property
    def event_bus(self) -> "EventBus":
        """Event bus para comunicación entre componentes."""
        if self._event_bus is None:
            from backend.app.infrastructure.event_bus import EventBus
            self._event_bus = EventBus(
                max_queue_size=self.legacy_settings.event_bus_max_queue_size
            )
        return self._event_bus
    
    @property
    def market_state(self) -> "MarketStateManager":
        """Estado del mercado (velas, precios)."""
        if self._market_state is None:
            from backend.app.state.market_state import MarketStateManager
            self._market_state = MarketStateManager()
        return self._market_state
    
    @property
    def indicator_state(self) -> "IndicatorStateManager":
        """Estado de indicadores técnicos."""
        if self._indicator_state is None:
            from backend.app.state.indicator_state import IndicatorStateManager
            self._indicator_state = IndicatorStateManager()
        return self._indicator_state
    
    @property
    def trade_state(self) -> "TradeStateManager":
        """Estado de trades simulados."""
        if self._trade_state is None:
            from backend.app.state.trade_state import TradeStateManager
            self._trade_state = TradeStateManager()
        return self._trade_state
    
    @property
    def candle_builder(self) -> "CandleBuilder":
        """Constructor de velas desde ticks."""
        if self._candle_builder is None:
            from backend.app.services.candle_builder import CandleBuilder
            self._candle_builder = CandleBuilder(
                interval=self.legacy_settings.candle_interval_seconds
            )
        return self._candle_builder
    
    @property
    def indicator_service(self) -> "IndicatorService":
        """Servicio de cálculo de indicadores."""
        if self._indicator_service is None:
            from backend.app.services.indicator_service import IndicatorService
            self._indicator_service = IndicatorService(
                state_manager=self.indicator_state
            )
        return self._indicator_service
    
    @property
    def sr_service(self) -> "SupportResistanceService":
        """Servicio de soportes y resistencias."""
        if self._sr_service is None:
            from backend.app.services.support_resistance_service import SupportResistanceService
            self._sr_service = SupportResistanceService(
                max_levels=self.legacy_settings.signal_sr_max_levels,
                sr_tolerance_pct=self.legacy_settings.signal_sr_tolerance_pct,
                breakout_candle_mult=self.legacy_settings.signal_breakout_candle_mult,
                consolidation_candles=self.legacy_settings.signal_consolidation_candles,
                consolidation_atr_mult=self.legacy_settings.signal_consolidation_atr_mult,
            )
        return self._sr_service
    
    @property
    def signal_engine(self) -> "SignalEngine":
        """Motor de generación de señales."""
        if self._signal_engine is None:
            from backend.app.services.signal_engine import SignalEngine
            self._signal_engine = SignalEngine(
                sr_service=self.sr_service,
                min_confirmations=self.legacy_settings.signal_min_confirmations,
                rr_ratio=self.legacy_settings.signal_rr_ratio,
                min_rr=self.legacy_settings.signal_min_rr,
                rsi_oversold=self.legacy_settings.signal_rsi_oversold,
                rsi_overbought=self.legacy_settings.signal_rsi_overbought,
                min_sl_pct=self.legacy_settings.signal_min_sl_pct,
                cooldown_candles=self.legacy_settings.signal_cooldown_candles,
                candle_interval=self.legacy_settings.candle_interval_seconds,
            )
        return self._signal_engine
    
    @property
    def stats_engine(self) -> "StatsEngine":
        """Motor de estadísticas."""
        if self._stats_engine is None:
            from backend.app.services.stats_engine import StatsEngine
            self._stats_engine = StatsEngine(trade_state=self.trade_state)
        return self._stats_engine
    
    @property
    def trade_simulator(self) -> "TradeSimulator":
        """Simulador de trades (paper trading)."""
        if self._trade_simulator is None:
            from backend.app.services.trade_simulator import TradeSimulator
            self._trade_simulator = TradeSimulator(
                trade_state=self.trade_state,
                stats_engine=self.stats_engine
            )
        return self._trade_simulator
    
    @property
    def tf_aggregator(self) -> "TimeframeAggregator":
        """Agregador de timeframes."""
        if self._tf_aggregator is None:
            from backend.app.services.timeframe_aggregator import TimeframeAggregator
            self._tf_aggregator = TimeframeAggregator(
                timeframes=self.legacy_settings.available_timeframes
            )
        return self._tf_aggregator
    
    @property
    def deriv_client(self) -> "DerivClient":
        """Cliente de conexión a Deriv."""
        if self._deriv_client is None:
            from backend.app.infrastructure.deriv_client import DerivClient
            self._deriv_client = DerivClient(event_bus=self.event_bus)
        return self._deriv_client
    
    @property
    def legacy_process_tick(self) -> "LegacyProcessTickUseCase":
        """ProcessTickUseCase legacy (backend.app)."""
        if self._legacy_process_tick is None:
            from backend.app.application.process_tick_usecase import ProcessTickUseCase
            self._legacy_process_tick = ProcessTickUseCase(
                event_bus=self.event_bus,
                candle_builder=self.candle_builder,
                market_state=self.market_state,
                indicator_service=self.indicator_service,
                sr_service=self.sr_service,
                signal_engine=self.signal_engine,
                trade_simulator=self.trade_simulator,
                tf_aggregator=self.tf_aggregator,
                active_timeframe=self.legacy_settings.default_timeframe,
            )
        return self._legacy_process_tick
    
    @property
    def ws_manager(self) -> "WebSocketManager":
        """WebSocket manager para broadcast a frontend."""
        if self._ws_manager is None:
            from backend.app.api.websocket_manager import WebSocketManager
            self._ws_manager = WebSocketManager(event_bus=self.event_bus)
        return self._ws_manager
    
    # ==================== Lifecycle ====================
    
    def reset(self) -> None:
        """Resetea todas las instancias (útil para tests)."""
        # Clean Architecture
        self._signal_repository = None
        self._trade_repository = None
        self._event_publisher = None
        self._market_data_provider = None
        self._ml_predictor = None
        self._signal_rules = None
        self._risk_calculator = None
        self._indicator_calculator = None
        # Legacy
        self._event_bus = None
        self._market_state = None
        self._indicator_state = None
        self._trade_state = None
        self._candle_builder = None
        self._indicator_service = None
        self._sr_service = None
        self._signal_engine = None
        self._trade_simulator = None
        self._stats_engine = None
        self._tf_aggregator = None
        self._deriv_client = None
        self._legacy_process_tick = None
        self._ws_manager = None
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
