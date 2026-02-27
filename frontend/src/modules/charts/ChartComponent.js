/**
 * QuantPulse – Chart Component (Candlestick + EMA + RSI)
 * ========================================================
 * Gráfico principal con candlestick, EMAs y RSI usando Canvas 2D.
 * 
 * Extiende BaseComponent para gestión de lifecycle y Store subscriptions.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { EventBus } from '../../core/eventBus.js';
import {
  CHART_COLORS,
  formatPrice,
  debounce,
  getPriceScale,
  createPriceToY,
  drawPriceGrid,
  drawPriceScale,
  drawHorizontalLine,
} from './chartAdapter.js';

const RSI_PANEL_RATIO = 0.2;
const MAX_CANDLES = 200;

export class ChartComponent extends BaseComponent {
  constructor(canvasId) {
    super(canvasId);

    /** @type {HTMLCanvasElement} */
    this.canvas = this.element;
    /** @type {CanvasRenderingContext2D} */
    this.ctx = null;

    // Estado local del gráfico
    this._candles = [];
    this._indicators = [];
    this._rsiValues = [];
    this._signals = [];
    this._activeTrade = null;

    // Dimensiones
    this._width = 0;
    this._height = 0;
    this._dpr = 1;

    // Padding
    this._padLeft = 10;
    this._padRight = 60;
    this._padTop = 10;
    this._padBottom = 4;

    // Resize handler con debounce
    this._onResize = debounce(() => this._resizeCanvas(), 200);
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();

    if (!this.canvas) {
      console.error('[ChartComponent] Canvas no encontrado');
      return;
    }

    this.ctx = this.canvas.getContext('2d');
    this._resizeCanvas();

    // Resize listener
    window.addEventListener('resize', this._onResize);
    this._cleanups.push(() => window.removeEventListener('resize', this._onResize));

    // Suscribirse al Store
    this.subscribeToStore('market', (state) => this._onMarketStateChange(state));
    this.subscribeToStore('trading', (state) => this._onTradingStateChange(state));

    // Cargar datos iniciales
    this._loadInitialData();
  }

  _loadInitialData() {
    const state = Store.getState();
    const symbol = state.market?.currentSymbol;
    if (symbol && state.market?.candles?.[symbol]) {
      this._candles = state.market.candles[symbol].slice();
    }
    if (symbol && state.market?.indicators?.[symbol]) {
      this._indicators = state.market.indicators[symbol].slice();
    }
    this.scheduleRender();
  }

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onMarketStateChange(market) {
    const symbol = market.currentSymbol;
    
    // Actualizar velas
    if (market.candles?.[symbol]) {
      this._candles = market.candles[symbol].slice();
    }
    
    // Actualizar indicadores
    if (market.indicators?.[symbol]) {
      this._updateIndicators(market.indicators[symbol]);
    }

    this.scheduleRender();
  }

  _updateIndicators(indicators) {
    // Extraer EMAs y RSI de los indicadores
    this._indicators = [];
    this._rsiValues = [];

    for (const ind of indicators) {
      this._indicators.push({
        ema_9: ind.ema_9,
        ema_21: ind.ema_21,
      });
      if (ind.rsi_14 !== null && ind.rsi_14 !== undefined) {
        this._rsiValues.push(ind.rsi_14);
      }
    }

    // Limitar
    if (this._indicators.length > MAX_CANDLES) {
      this._indicators = this._indicators.slice(-MAX_CANDLES);
    }
    if (this._rsiValues.length > MAX_CANDLES) {
      this._rsiValues = this._rsiValues.slice(-MAX_CANDLES);
    }
  }

  _onTradingStateChange(trading) {
    const symbol = Store.getState().market?.currentSymbol;
    
    // Actualizar señales
    this._signals = (trading.signals || [])
      .filter(s => s.symbol === symbol)
      .slice(-20);

    // Trade activo
    const openTrades = trading.openTrades || [];
    this._activeTrade = openTrades.find(t => t.symbol === symbol) || null;

    this.scheduleRender();
  }

  // ─────────────────────────────────────────────────────────
  // Canvas resize
  // ─────────────────────────────────────────────────────────

  _resizeCanvas() {
    const parent = this.canvas.parentElement;
    if (!parent) return;

    this._dpr = window.devicePixelRatio || 1;
    this._width = parent.clientWidth;
    this._height = parent.clientHeight;

    this.canvas.width = this._width * this._dpr;
    this.canvas.height = this._height * this._dpr;
    this.canvas.style.width = this._width + 'px';
    this.canvas.style.height = this._height + 'px';

    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(this._dpr, this._dpr);

    this.scheduleRender();
  }

  // ─────────────────────────────────────────────────────────
  // Render principal
  // ─────────────────────────────────────────────────────────

  render() {
    if (!this.ctx) return;

    const W = this._width;
    const H = this._height;
    const candles = this._candles;

    // Limpiar
    this.ctx.fillStyle = CHART_COLORS.bg;
    this.ctx.fillRect(0, 0, W, H);

    if (candles.length === 0) {
      this._drawNoData(W, H);
      return;
    }

    // Dividir altura: 80% precio, 20% RSI
    const priceH = H * (1 - RSI_PANEL_RATIO);
    const rsiH = H * RSI_PANEL_RATIO;
    const rsiTop = priceH;

    // Calcular escala de precios
    const { min: minP, max: maxP } = getPriceScale(candles, 0.02);
    const priceToY = createPriceToY(minP, maxP, priceH, this._padTop, this._padBottom);

    // Espaciado de velas
    const candleSpace = (W - this._padLeft - this._padRight) / candles.length;

    // ── Dibujar componentes ───────────────────────────────
    this._drawPriceGrid(W, priceH, minP, maxP, priceToY);
    this._drawCandles(candles, candleSpace, priceToY);
    this._drawEMAs(candles, candleSpace, priceToY);
    this._drawSignals(candles, candleSpace, priceToY);
    this._drawActiveTrade(W, minP, maxP, priceToY);
    this._drawPriceScale(W, priceH, minP, maxP, priceToY);
    this._drawLastPrice(candles, W, priceToY);
    
    // Panel RSI
    this._drawRSIPanel(W, rsiTop, rsiH, candles.length, candleSpace);
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: Grid y escala
  // ─────────────────────────────────────────────────────────

  _drawNoData(W, H) {
    this.ctx.fillStyle = CHART_COLORS.gridText;
    this.ctx.font = '14px monospace';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('Sin datos de mercado', W / 2, H / 2);
  }

  _drawPriceGrid(W, H, minP, maxP, priceToY) {
    drawPriceGrid(this.ctx, {
      width: W,
      height: H,
      padLeft: this._padLeft,
      padRight: this._padRight,
      minPrice: minP,
      maxPrice: maxP,
      priceToY,
      steps: 6,
    });
  }

  _drawPriceScale(W, H, minP, maxP, priceToY) {
    drawPriceScale(this.ctx, {
      width: W,
      padRight: this._padRight,
      minPrice: minP,
      maxPrice: maxP,
      priceToY,
      steps: 6,
    });
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: Velas
  // ─────────────────────────────────────────────────────────

  _drawCandles(candles, spacing, priceToY) {
    const ctx = this.ctx;
    const padL = this._padLeft;
    const candleW = Math.max(1, spacing * 0.6);
    const wickW = Math.max(1, spacing * 0.1);

    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const x = padL + (i + 0.5) * spacing;
      const isBullish = c.close >= c.open;
      const color = isBullish ? CHART_COLORS.bullish : CHART_COLORS.bearish;

      // Mecha
      ctx.strokeStyle = CHART_COLORS.wick;
      ctx.lineWidth = wickW;
      ctx.beginPath();
      ctx.moveTo(x, priceToY(c.high));
      ctx.lineTo(x, priceToY(c.low));
      ctx.stroke();

      // Cuerpo
      const yOpen = priceToY(c.open);
      const yClose = priceToY(c.close);
      const bodyTop = Math.min(yOpen, yClose);
      const bodyH = Math.max(1, Math.abs(yOpen - yClose));

      ctx.fillStyle = color;
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
    }
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: EMAs
  // ─────────────────────────────────────────────────────────

  _drawEMAs(candles, spacing, priceToY) {
    const indicators = this._indicators;
    if (indicators.length === 0) return;

    const offset = candles.length - indicators.length;

    this._drawEMALine('ema_9', CHART_COLORS.ema9, spacing, priceToY, offset);
    this._drawEMALine('ema_21', CHART_COLORS.ema21, spacing, priceToY, offset);
  }

  _drawEMALine(key, color, spacing, priceToY, offset) {
    const ctx = this.ctx;
    const indicators = this._indicators;
    const padL = this._padLeft;

    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();

    let started = false;
    for (let i = 0; i < indicators.length; i++) {
      const val = indicators[i][key];
      if (val === null || val === undefined) continue;

      const x = padL + (i + offset + 0.5) * spacing;
      const y = priceToY(val);

      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: Señales
  // ─────────────────────────────────────────────────────────

  _drawSignals(candles, spacing, priceToY) {
    const ctx = this.ctx;
    const padL = this._padLeft;

    for (const sig of this._signals) {
      // Encontrar vela por timestamp
      const idx = candles.findIndex(c =>
        Math.abs(c.timestamp - sig.candle_timestamp) < 10
      );
      if (idx < 0) continue;

      const x = padL + (idx + 0.5) * spacing;
      const isBuy = sig.signal_type === 'BUY';
      const candleY = priceToY(isBuy ? candles[idx].low : candles[idx].high);

      // Triángulo
      ctx.fillStyle = isBuy ? CHART_COLORS.signalBuy : CHART_COLORS.signalSell;
      ctx.beginPath();

      if (isBuy) {
        ctx.moveTo(x, candleY + 4);
        ctx.lineTo(x - 5, candleY + 14);
        ctx.lineTo(x + 5, candleY + 14);
      } else {
        ctx.moveTo(x, candleY - 4);
        ctx.lineTo(x - 5, candleY - 14);
        ctx.lineTo(x + 5, candleY - 14);
      }

      ctx.closePath();
      ctx.fill();
    }
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: TP/SL
  // ─────────────────────────────────────────────────────────

  _drawActiveTrade(W, minP, maxP, priceToY) {
    if (!this._activeTrade) return;

    const trade = this._activeTrade;

    // Entry
    drawHorizontalLine(this.ctx, {
      price: trade.entry_price,
      color: CHART_COLORS.lastPrice,
      label: `Entry: ${formatPrice(trade.entry_price)}`,
      width: W,
      padLeft: this._padLeft,
      padRight: this._padRight,
      priceToY,
      minPrice: minP,
      maxPrice: maxP,
      dashed: true,
    });

    // Take Profit
    if (trade.take_profit) {
      drawHorizontalLine(this.ctx, {
        price: trade.take_profit,
        color: CHART_COLORS.tpLine,
        label: `TP: ${formatPrice(trade.take_profit)}`,
        width: W,
        padLeft: this._padLeft,
        padRight: this._padRight,
        priceToY,
        minPrice: minP,
        maxPrice: maxP,
        dashed: true,
      });
    }

    // Stop Loss
    if (trade.stop_loss) {
      drawHorizontalLine(this.ctx, {
        price: trade.stop_loss,
        color: CHART_COLORS.slLine,
        label: `SL: ${formatPrice(trade.stop_loss)}`,
        width: W,
        padLeft: this._padLeft,
        padRight: this._padRight,
        priceToY,
        minPrice: minP,
        maxPrice: maxP,
        dashed: true,
      });
    }
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: Último precio
  // ─────────────────────────────────────────────────────────

  _drawLastPrice(candles, W, priceToY) {
    if (candles.length === 0) return;

    const lastCandle = candles[candles.length - 1];
    const price = lastCandle.close;
    const y = priceToY(price);
    const ctx = this.ctx;

    // Línea horizontal
    ctx.strokeStyle = CHART_COLORS.lastPrice;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(this._padLeft, y);
    ctx.lineTo(W - this._padRight, y);
    ctx.stroke();
    ctx.setLineDash([]);

    // Label con fondo
    const labelText = formatPrice(price);
    const labelW = ctx.measureText(labelText).width + 8;
    const labelH = 16;
    const labelX = W - this._padRight + 2;
    const labelY = y - labelH / 2;

    ctx.fillStyle = CHART_COLORS.lastPrice;
    ctx.fillRect(labelX, labelY, labelW, labelH);

    ctx.fillStyle = CHART_COLORS.bg;
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(labelText, labelX + 4, y + 4);
  }

  // ─────────────────────────────────────────────────────────
  // Dibujo: RSI Panel
  // ─────────────────────────────────────────────────────────

  _drawRSIPanel(W, top, height, candleCount, spacing) {
    const ctx = this.ctx;
    const padL = this._padLeft;
    const padR = this._padRight;
    const rsiValues = this._rsiValues;

    // Fondo del panel
    ctx.fillStyle = '#0a0d10';
    ctx.fillRect(0, top, W, height);

    // Separador
    ctx.strokeStyle = CHART_COLORS.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, top);
    ctx.lineTo(W, top);
    ctx.stroke();

    // Zonas oversold/overbought
    const rsiToY = (val) => top + (1 - val / 100) * height;

    ctx.fillStyle = CHART_COLORS.rsiOverBought;
    ctx.fillRect(padL, rsiToY(100), W - padL - padR, rsiToY(70) - rsiToY(100));

    ctx.fillStyle = CHART_COLORS.rsiOverSold;
    ctx.fillRect(padL, rsiToY(30), W - padL - padR, rsiToY(0) - rsiToY(30));

    // Líneas de nivel
    ctx.strokeStyle = CHART_COLORS.rsiZone;
    ctx.lineWidth = 0.5;
    ctx.setLineDash([2, 2]);

    for (const level of [30, 50, 70]) {
      const y = rsiToY(level);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(W - padR, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // Labels
    ctx.fillStyle = CHART_COLORS.gridText;
    ctx.font = '9px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('70', W - padR + 4, rsiToY(70) + 3);
    ctx.fillText('30', W - padR + 4, rsiToY(30) + 3);

    // Dibujar línea RSI
    if (rsiValues.length < 2) return;

    const offset = candleCount - rsiValues.length;
    ctx.strokeStyle = CHART_COLORS.rsiLine;
    ctx.lineWidth = 1.5;
    ctx.beginPath();

    let started = false;
    for (let i = 0; i < rsiValues.length; i++) {
      const val = rsiValues[i];
      if (val === null || val === undefined) continue;

      const x = padL + (i + offset + 0.5) * spacing;
      const y = rsiToY(val);

      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    // Valor actual
    if (rsiValues.length > 0) {
      const lastRsi = rsiValues[rsiValues.length - 1];
      ctx.fillStyle = CHART_COLORS.rsiLine;
      ctx.font = 'bold 10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`RSI: ${lastRsi?.toFixed(1) || '--'}`, W - padR - 4, top + 14);
    }
  }

  // ─────────────────────────────────────────────────────────
  // API pública
  // ─────────────────────────────────────────────────────────

  /**
   * Forzar actualización del gráfico.
   */
  refresh() {
    this.scheduleRender();
  }

  /**
   * Limpiar y resetear.
   */
  clear() {
    this._candles = [];
    this._indicators = [];
    this._rsiValues = [];
    this._signals = [];
    this._activeTrade = null;
    this.scheduleRender();
  }
}

export default ChartComponent;
