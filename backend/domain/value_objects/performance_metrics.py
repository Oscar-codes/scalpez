"""
QuantPulse - Performance Metrics (Value Object)
=====================================================
Estructura inmutable que contiene todas las metricas cuantitativas
calculadas por el StatsEngine sobre un conjunto de trades cerrados.

PRINCIPIO DE DISENO:
  Es un VALUE OBJECT puro: no tiene identidad, no muta, no tiene
  logica de negocio. Solo transporta datos ya calculados.
  Usa frozen dataclass para inmutabilidad garantizada.

POR QUE FROZEN:
  Las metricas son una foto instantanea. Una vez calculadas,
  no deben cambiar. Si llega un nuevo trade, se genera un
  PerformanceMetrics NUEVO (recalculo completo O(n)).
  Esto facilita comparacion temporal y futura persistencia.

PREPARACION PARA BACKTESTING:
  El mismo PerformanceMetrics sirve tanto para paper trading en
  tiempo real como para backtesting offline. La unica diferencia
  es la fuente de trades: en vivo vienen del TradeSimulator,
  en backtest vendran de un HistoricalTradeLoader.
  La interfaz del StatsEngine no cambia.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    """
    Metricas cuantitativas de performance de trading.

    Atributos:
    ----------
    total_trades : int
        N total de trades cerrados analizados.

    wins : int
        Trades cerrados con PnL > 0 (status = PROFIT).

    losses : int
        Trades cerrados con PnL <= 0 excluyendo expirados con PnL = 0.

    expired : int
        Trades cerrados por expiracion temporal.

    win_rate : float
        Porcentaje de trades ganadores: (wins / total) * 100.
        Rango: [0.0, 100.0].

    loss_rate : float
        Porcentaje de trades perdedores: 100.0 - win_rate.

    profit_factor : float
        POR QUE ES MAS RELEVANTE QUE WIN RATE:
        ─────────────────────────────────────────
        Un sistema puede tener win_rate=30% y ser muy rentable si
        las ganancias promedio son 5x las perdidas (PF > 1.5).
        Inversamente, un 70% win_rate puede ser perdedor si las
        perdidas promedio son 3x las ganancias (PF < 1.0).

        PF = gross_profit / gross_loss

        PF > 1.0  ->  sistema rentable en promedio
        PF > 1.5  ->  edge significativo
        PF > 2.0  ->  sistema muy robusto
        PF < 1.0  ->  sistema perdedor neto

        0.0 si no hay perdidas (division protegida).

    expectancy : float
        COMO SE CALCULA EXPECTANCY CORRECTAMENTE:
        ────────────────────────────────────────────
        Expectancy = (WinRate * AvgWin) - (LossRate * AvgLoss)

        Donde:
          WinRate  = wins / total (como fraccion, no porcentaje)
          LossRate = losses / total (misma fraccion)
          AvgWin   = promedio de PnL% de trades ganadores
          AvgLoss  = promedio de |PnL%| de trades perdedores (valor absoluto)

        Interpretacion:
          Expectancy > 0  ->  esperanza matematica positiva (edge real)
          Expectancy = 0  ->  break-even, sin ventaja estadistica
          Expectancy < 0  ->  esperanza negativa, estrategia perdedora

        COMO DETECTAR SI UNA ESTRATEGIA TIENE EDGE REAL:
        ───────────────────────────────────────────────────
        1. Expectancy > 0 de forma consistente.
        2. Profit Factor > 1.2 sostenido.
        3. El edge persiste tras descontar costos (spread, slippage).
        4. El sample size es suficiente (>30 trades minimo, idealmente >100).
        5. El max_drawdown es tolerable para el capital disponible.

        ATENCION: en tiempo real el sample size crece gradualmente.
        Con <30 trades, las metricas tienen alta varianza y no deben
        usarse para decisiones definitivas sobre la estrategia.

    avg_rr_real : float
        Risk-Reward ratio real promedio de trades cerrados.
        Se calcula como: avg(|pnl_profit| / |pnl_loss|) por trade
        individual cuando ambos componentes estan disponibles.
        Alternativa: avg_win / avg_loss global.

    avg_duration : float
        Duracion promedio de trades en segundos.

    max_drawdown : float
        DRAWDOWN MAXIMO SIMPLE:
        ─────────────────────────
        Se construye la equity curve acumulada (suma de PnL% por trade).
        En cada punto, se calcula:
          drawdown_i = peak_equity - equity_i
          max_drawdown = max(drawdown_i) para todo i

        Representa la peor caida desde un pico en la curva de equity.
        Es la metrica de riesgo mas importante para sizing.

    equity_curve : tuple[float, ...]
        Equity acumulada punto a punto (inmutable como tuple).
        equity_curve[i] = sum(pnl_percent[0:i+1])

        Uso: visualizacion en frontend, deteccion de regimenes.
        Es tuple (no list) para respetar frozen=True.

    gross_profit : float
        Suma de todos los PnL% positivos.

    gross_loss : float
        Valor absoluto de la suma de todos los PnL% negativos.

    avg_win : float
        PnL% promedio de trades ganadores.

    avg_loss : float
        |PnL%| promedio de trades perdedores (valor absoluto).

    best_trade : float
        Mayor PnL% individual.

    worst_trade : float
        Menor PnL% individual (mas negativo).

    total_pnl : float
        Suma total de PnL% de todos los trades.

    LIMITACIONES DEL ANALISIS EN TIEMPO REAL:
    ──────────────────────────────────────────
    1. Sample size pequeno al inicio -> metricas inestables.
    2. Regimenes de mercado cambian -> metricas pasadas no predicen futuro.
    3. No hay costos de ejecucion modelados (spread, comision).
    4. Derivados sinteticos de Deriv no reflejan mercados reales.
    5. El drawdown puede empeorar en cualquier momento.
    6. Survivorship bias: solo vemos trades ejecutados, no los filtrados.

    COMO PREPARAR EL SISTEMA PARA BACKTESTING FUTURO:
    ──────────────────────────────────────────────────
    1. PerformanceMetrics es independiente de la fuente de trades.
    2. StatsEngine.compute(trades) acepta cualquier lista de trades.
    3. Solo se necesita un HistoricalTradeLoader que genere la misma
       estructura SimulatedTrade a partir de datos historicos.
    4. La persistencia en DB (futuro) almacenara trades con el mismo
       schema, permitiendo calculos offline identicos.
    """

    # ── Contadores ──────────────────────────────────────────────────
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0

    # ── Ratios ──────────────────────────────────────────────────────
    win_rate: float = 0.0
    loss_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_rr_real: float = 0.0

    # ── Temporales ──────────────────────────────────────────────────
    avg_duration: float = 0.0

    # ── Riesgo ──────────────────────────────────────────────────────
    max_drawdown: float = 0.0
    equity_curve: tuple = field(default_factory=tuple)

    # ── PnL detallado ──────────────────────────────────────────────
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    total_pnl: float = 0.0

    def to_dict(self) -> dict:
        """Serializacion para API REST / WebSocket / persistencia."""
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "expired": self.expired,
            "win_rate": round(self.win_rate, 2),
            "loss_rate": round(self.loss_rate, 2),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "avg_rr_real": round(self.avg_rr_real, 4),
            "avg_duration": round(self.avg_duration, 1),
            "max_drawdown": round(self.max_drawdown, 4),
            "equity_curve": [round(e, 4) for e in self.equity_curve],
            "gross_profit": round(self.gross_profit, 4),
            "gross_loss": round(self.gross_loss, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "best_trade": round(self.best_trade, 4),
            "worst_trade": round(self.worst_trade, 4),
            "total_pnl": round(self.total_pnl, 4),
        }
