"""
QuantPulse - Stats Engine (Performance Analytics)
=====================================================
Motor de analisis cuantitativo de performance sobre trades cerrados.

PRINCIPIO CENTRAL:
  Todas las metricas se calculan en una UNICA PASADA O(n) sobre la
  lista de trades cerrados. No se usa pandas ni librerias externas.
  Python puro optimizado con acumuladores incrementales.

CUANDO SE EJECUTA:
  - Al cerrar un trade (el TradeSimulator notifica).
  - Bajo demanda via API (/api/stats, /api/stats/{symbol}).
  - NO en cada tick (seria O(n) innecesario por tick).

CACHE INTELIGENTE:
  Se usa un contador de version (_version) sincronizado con el numero
  de trades cerrados. Si no cambia, se devuelve el cache.
  Esto evita recalcular cuando no hay trades nuevos.

  _cached_metrics: PerformanceMetrics | None
  _cached_version: int  (count de trades cerrados al momento del cache)

  Si el count actual == _cached_version → devolver cache.
  Si el count actual != _cached_version → recalcular O(n) → actualizar cache.

PREPARACION PARA BACKTESTING:
  compute() recibe list[SimulatedTrade] puro. No depende del estado
  global, ni del event bus, ni de asyncio. Es una funcion pura.
  Para backtesting, se puede llamar directamente con trades historicos.

COMPLEJIDAD ALGORITMICA:
  compute()        → O(n) una pasada, n = numero de trades
  equity_curve     → O(n) calculada inline (no requiere pasada extra)
  max_drawdown     → O(n) calculado inline durante equity_curve
  filtro por simbolo → O(n) en peor caso (podria optimizarse con dict)

══════════════════════════════════════════════════════════════════
  FORMULAS CUANTITATIVAS (referencia rapida)
══════════════════════════════════════════════════════════════════

  Win Rate     = wins / total * 100
  Loss Rate    = 100 - Win Rate

  Profit Factor = gross_profit / gross_loss
    PF > 1.0 → rentable    PF > 1.5 → edge    PF > 2.0 → robusto

  Expectancy = (WR_frac * AvgWin) - (LR_frac * AvgLoss)
    > 0 → esperanza positiva    < 0 → estrategia perdedora

  Avg RR Real = avg_win / avg_loss   (si avg_loss > 0)

  Max Drawdown = max(peak_i - equity_i)  para todo i
    Sobre la equity curve acumulada de PnL%.

══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Optional

from ..domain.entities.trade import SimulatedTrade, TradeStatus
from ..domain.entities.value_objects.performance_metrics import PerformanceMetrics
from ..state.trade_state import TradeStateManager

logger = logging.getLogger("quantpulse.stats_engine")

# Metricas vacias para cuando no hay trades
_EMPTY_METRICS = PerformanceMetrics()


class StatsEngine:
    """
    Motor de performance analytics cuantitativo.

    Responsabilidades:
      1. Calcular metricas sobre trades cerrados en O(n).
      2. Cachear resultados para evitar recalculos innecesarios.
      3. Soportar filtro por simbolo.
      4. Proveer datos listos para API/frontend/persistencia.

    POR QUE PROFIT FACTOR ES MAS RELEVANTE QUE WIN RATE:
    ──────────────────────────────────────────────────────
    Win Rate solo mide frecuencia de exito, no magnitud. Un sistema
    con 30% WR pero avg_win = 5 * avg_loss tiene PF = 2.14 y es
    altamente rentable. Un sistema con 80% WR pero avg_win = 0.1 *
    avg_loss tiene PF = 0.4 y es desastroso. Profit Factor captura
    ambas dimensiones en un solo numero.

    COMO DETECTAR SI LA ESTRATEGIA TIENE EDGE REAL:
    ────────────────────────────────────────────────
    1. Expectancy > 0 consistente (no solo en una sesion).
    2. Profit Factor > 1.2 sostenido en >50 trades.
    3. El edge sobrevive despues de descontar slippage real
       (que ya modelamos con entry_price != signal_entry).
    4. La equity curve muestra tendencia ascendente, no lateralidad.
    5. El max_drawdown es recuperable (no >50% del equity ficticio).

    LIMITACIONES DEL ANALISIS EN TIEMPO REAL:
    ──────────────────────────────────────────
    1. N pequeno al inicio → metricas con alta varianza.
    2. Regimenes de mercado cambiantes invalidan statisticas pasadas.
    3. No modelamos costos de spread/comision (Deriv sinteticos).
    4. Survivorship bias: solo medimos trades ejecutados.
    5. La equity curve puede empeorar en cualquier momento futuro.
    """

    def __init__(self, trade_state: TradeStateManager) -> None:
        self._trade_state = trade_state

        # ── Cache por simbolo (None = global) ──
        # key: symbol | "__global__"
        # value: (version_count, PerformanceMetrics)
        self._cache: dict[str, tuple[int, PerformanceMetrics]] = {}

    # ═══════════════════════════════════════════════════════════════
    #  API PUBLICA
    # ═══════════════════════════════════════════════════════════════

    def on_trade_closed(self, trade: SimulatedTrade) -> None:
        """
        Callback cuando un trade se cierra.
        Invalida el cache para el simbolo del trade y el global.
        El recalculo ocurre lazy en la proxima consulta.
        """
        # Invalidar caches afectados
        self._cache.pop(trade.symbol, None)
        self._cache.pop("__global__", None)

        logger.info(
            "Stats invalidadas | sym=%s trade=%s status=%s pnl=%.4f%%",
            trade.symbol, trade.id, trade.status.value, trade.pnl_percent,
        )

    def get_metrics(self, symbol: Optional[str] = None) -> PerformanceMetrics:
        """
        Obtiene metricas (de cache o recalculando).

        Args:
            symbol: Filtrar por simbolo. None = metricas globales.

        Returns:
            PerformanceMetrics inmutable con todas las metricas.
        """
        cache_key = symbol or "__global__"
        trades = self._trade_state.get_closed_trades(symbol=symbol)
        current_count = len(trades)

        # ── Cache hit? ──
        if cache_key in self._cache:
            cached_count, cached_metrics = self._cache[cache_key]
            if cached_count == current_count and current_count > 0:
                return cached_metrics

        # ── Cache miss → recalcular ──
        if current_count == 0:
            return _EMPTY_METRICS

        # Ordenar por close_timestamp ascendente para equity curve
        trades_sorted = sorted(trades, key=lambda t: t.close_timestamp)
        metrics = self.compute(trades_sorted)

        # Guardar en cache
        self._cache[cache_key] = (current_count, metrics)

        logger.debug(
            "Stats recalculadas | key=%s trades=%d PF=%.2f Exp=%.4f WR=%.1f%%",
            cache_key, current_count,
            metrics.profit_factor, metrics.expectancy, metrics.win_rate,
        )

        return metrics

    def get_all_metrics(self) -> dict:
        """
        Metricas globales + por simbolo. Listo para API.
        """
        global_metrics = self.get_metrics(symbol=None)

        # Detectar simbolos con trades cerrados
        all_trades = self._trade_state.get_closed_trades(symbol=None)
        symbols = set(t.symbol for t in all_trades)

        by_symbol = {}
        for sym in sorted(symbols):
            by_symbol[sym] = self.get_metrics(symbol=sym).to_dict()

        return {
            "global": global_metrics.to_dict(),
            "by_symbol": by_symbol,
        }

    # ═══════════════════════════════════════════════════════════════
    #  COMPUTE - CALCULO O(n) EN UNA PASADA
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def compute(trades: list[SimulatedTrade]) -> PerformanceMetrics:
        """
        Calcula TODAS las metricas en una unica pasada O(n).

        El algoritmo recorre la lista una sola vez acumulando:
          - contadores (wins, losses, expired)
          - sumas parciales (gross_profit, gross_loss, duraciones)
          - equity curve + max_drawdown inline
          - extremos (best, worst)

        Al final, calcula ratios derivados (WR, PF, Exp, RR) con
        proteccion contra division por cero.

        Args:
            trades: Lista de SimulatedTrade cerrados, ordenados por
                    close_timestamp ascendente (para equity curve).

        Returns:
            PerformanceMetrics inmutable.

        Complejidad:
            Tiempo:  O(n)
            Espacio: O(n) por equity_curve, O(1) para acumuladores.

        COMO PREPARAR PARA BACKTESTING:
        ────────────────────────────────
        Esta funcion es PURA: no depende de estado global, asyncio,
        ni EventBus. Se le puede pasar cualquier lista de trades
        generados por un backtester historico y devuelve las mismas
        metricas exactas. Solo se necesita que los trades sean
        SimulatedTrade con pnl_percent, duration_seconds, etc.
        """
        if not trades:
            return _EMPTY_METRICS

        n = len(trades)

        # ── Acumuladores (una sola pasada) ──────────────────────────
        wins = 0
        losses = 0
        expired = 0
        gross_profit = 0.0
        gross_loss = 0.0
        sum_duration = 0.0
        best_pnl = float("-inf")
        worst_pnl = float("inf")

        # Equity curve + max drawdown inline
        equity_points: list[float] = []
        cumulative_equity = 0.0
        peak_equity = 0.0
        max_dd = 0.0

        # ── PASADA UNICA O(n) ──────────────────────────────────────
        for trade in trades:
            pnl = trade.pnl_percent

            # (1) Clasificar
            if trade.status == TradeStatus.PROFIT:
                wins += 1
            elif trade.status == TradeStatus.LOSS:
                losses += 1
            elif trade.status == TradeStatus.EXPIRED:
                expired += 1
                # Un EXPIRED tambien cuenta como win o loss segun su PnL
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1

            # (2) Acumular PnL
            if pnl > 0:
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)

            # (3) Extremos
            if pnl > best_pnl:
                best_pnl = pnl
            if pnl < worst_pnl:
                worst_pnl = pnl

            # (4) Duracion
            sum_duration += trade.duration_seconds

            # ─── (5) Equity curve + max drawdown inline ─────────
            #
            # COMO SE CALCULA MAX DRAWDOWN:
            #
            #   equity_i = equity_{i-1} + pnl_i
            #   peak_i   = max(peak_{i-1}, equity_i)
            #   dd_i     = peak_i - equity_i
            #   max_dd   = max(max_dd, dd_i)
            #
            # Esto detecta la mayor caida desde cualquier pico previo
            # en la curva de equity acumulada. Es la metrica de riesgo
            # mas importante para determinar tamanio de posicion.
            #
            cumulative_equity += pnl
            equity_points.append(cumulative_equity)

            if cumulative_equity > peak_equity:
                peak_equity = cumulative_equity

            dd = peak_equity - cumulative_equity
            if dd > max_dd:
                max_dd = dd

        # ── Calculos derivados (protegidos contra /0) ──────────────

        # Win/Loss counts para promedios (excluye expired con PnL=0)
        win_count = wins    # trades con PnL > 0 (incluye expired positivos)
        loss_count = losses  # trades con PnL < 0 (incluye expired negativos)

        # Win Rate / Loss Rate
        #   win_rate = wins / total * 100
        win_rate = (win_count / n) * 100.0 if n > 0 else 0.0
        loss_rate = 100.0 - win_rate

        # ── Profit Factor ──────────────────────────────────────────
        #
        # PF = gross_profit / gross_loss
        #
        # Interpretacion:
        #   PF > 1.0  → sistema rentable en promedio
        #   PF > 1.5  → edge significativo
        #   PF > 2.0  → sistema muy robusto
        #   PF = inf  → solo tiene ganadores (division por 0 protegida)
        #   PF < 1.0  → sistema perdedor
        #
        # Proteccion: si no hay perdidas, PF = 0 (indicando "no aplica"
        # en lugar de infinity, que romperia JSON serialization).
        #
        profit_factor = 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss

        # ── Promedios de ganadores/perdedores ──────────────────────
        avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0

        # ── Expectancy ─────────────────────────────────────────────
        #
        # COMO SE CALCULA CORRECTAMENTE:
        #
        #   Expectancy = (WR_frac * AvgWin) - (LR_frac * AvgLoss)
        #
        # Donde:
        #   WR_frac  = win_count / n   (fraccion, no porcentaje)
        #   LR_frac  = loss_count / n  (fraccion)
        #   AvgWin   = promedio PnL% de ganadores
        #   AvgLoss  = promedio |PnL%| de perdedores (absoluto)
        #
        # INTERPRETACION:
        #   Exp > 0  → cada trade tiene esperanza matematica positiva
        #   Exp = 0  → break-even exacto
        #   Exp < 0  → esperanza negativa, sistema perdedor a largo plazo
        #
        # EJEMPLO:
        #   WR=40%, AvgWin=+2.0%, AvgLoss=0.8%
        #   Exp = (0.4 * 2.0) - (0.6 * 0.8) = 0.8 - 0.48 = +0.32%
        #   → Cada trade espera ganar +0.32% en promedio. Edge real.
        #
        expectancy = 0.0
        if n > 0:
            wr_frac = win_count / n
            lr_frac = loss_count / n
            expectancy = (wr_frac * avg_win) - (lr_frac * avg_loss)

        # ── RR Real Promedio ───────────────────────────────────────
        #
        # CALCULO:
        #   avg_rr_real = avg_win / avg_loss
        #
        # Este es el RR "efectivo" que la estrategia entrega en la
        # practica, distinto del RR "teorico" (TP/SL ratio de la senal).
        # Si avg_rr_real < rr_teorico, hay slippage o salidas tempranas.
        #
        avg_rr_real = 0.0
        if avg_loss > 0:
            avg_rr_real = avg_win / avg_loss

        # ── Duracion promedio ──────────────────────────────────────
        avg_duration = sum_duration / n if n > 0 else 0.0

        # ── Proteccion de extremos para trades vacios ──────────────
        if best_pnl == float("-inf"):
            best_pnl = 0.0
        if worst_pnl == float("inf"):
            worst_pnl = 0.0

        total_pnl = gross_profit - gross_loss

        return PerformanceMetrics(
            total_trades=n,
            wins=win_count,
            losses=loss_count,
            expired=expired,
            win_rate=win_rate,
            loss_rate=loss_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_rr_real=avg_rr_real,
            avg_duration=avg_duration,
            max_drawdown=max_dd,
            equity_curve=tuple(equity_points),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best_pnl,
            worst_trade=worst_pnl,
            total_pnl=total_pnl,
        )
