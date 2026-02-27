/**
 * QuantPulse – Equity Curve Component
 * ======================================
 * Mini gráfico de equity curve usando Canvas.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { debounce, CHART_COLORS } from '../charts/chartAdapter.js';

export class EquityCurve extends BaseComponent {
  constructor(canvasId) {
    super(canvasId);
    
    /** @type {HTMLCanvasElement} */
    this.canvas = this.element;
    /** @type {CanvasRenderingContext2D} */
    this.ctx = null;
    
    this._width = 0;
    this._height = 0;
    this._dpr = 1;
    
    this._onResize = debounce(() => this._resize(), 200);
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    if (!this.canvas) return;
    
    this.ctx = this.canvas.getContext('2d');
    this._resize();
    
    // Resize listener
    window.addEventListener('resize', this._onResize);
    this._cleanups.push(() => window.removeEventListener('resize', this._onResize));
    
    // Suscribirse a cambios
    this.subscribeToStore('trading', () => this.scheduleRender());
    this.subscribeToStore('market', () => this.scheduleRender());
  }

  _resize() {
    if (!this.canvas) return;
    
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
  // Render
  // ─────────────────────────────────────────────────────────

  render() {
    if (!this.ctx || !this.canvas) return;
    
    const W = this._width;
    const H = this._height;
    const ctx = this.ctx;

    // Limpiar
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = CHART_COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    // Obtener datos
    const state = Store.getState();
    const stats = state.trading?.stats;
    
    if (!stats) {
      this._drawPlaceholder(W, H);
      return;
    }

    const symbol = state.market?.currentSymbol;
    const data = (stats.by_symbol && stats.by_symbol[symbol])
      ? stats.by_symbol[symbol]
      : stats.global || stats;

    const curve = data?.equity_curve;
    if (!curve || curve.length < 2) {
      this._drawPlaceholder(W, H);
      return;
    }

    // Incluir punto cero al inicio
    const points = [0, ...curve];

    // Padding
    const padL = 4;
    const padR = 4;
    const padT = 8;
    const padB = 8;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    // Calcular rango
    let minV = 0;
    let maxV = 0;
    for (const v of points) {
      if (v < minV) minV = v;
      if (v > maxV) maxV = v;
    }
    const range = (maxV - minV) || 1;
    minV -= range * 0.1;
    maxV += range * 0.1;
    const totalRange = maxV - minV;

    // Funciones de mapeo
    const toX = (i) => padL + (i / (points.length - 1)) * chartW;
    const toY = (v) => padT + (1 - (v - minV) / totalRange) * chartH;

    // Línea cero
    const zeroY = toY(0);
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 0.5;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(padL, zeroY);
    ctx.lineTo(W - padR, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Dibujar curva
    const lastVal = points[points.length - 1];
    const curveColor = lastVal >= 0 ? CHART_COLORS.bullish : CHART_COLORS.bearish;
    
    ctx.strokeStyle = curveColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    
    for (let i = 0; i < points.length; i++) {
      const x = toX(i);
      const y = toY(points[i]);
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    // Punto final
    const lastX = toX(points.length - 1);
    const lastY = toY(lastVal);
    
    ctx.fillStyle = curveColor;
    ctx.beginPath();
    ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
    ctx.fill();

    // Valor actual
    ctx.fillStyle = curveColor;
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'right';
    ctx.fillText(
      `${lastVal >= 0 ? '+' : ''}${lastVal.toFixed(3)}%`,
      W - padR - 4,
      padT + 12
    );

    // Label
    ctx.fillStyle = CHART_COLORS.gridText;
    ctx.font = '9px monospace';
    ctx.textAlign = 'left';
    ctx.fillText('Equity', padL + 4, H - padB - 4);
  }

  _drawPlaceholder(W, H) {
    const ctx = this.ctx;
    ctx.fillStyle = CHART_COLORS.gridText;
    ctx.font = '11px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('Equity Curve', W / 2, H / 2);
  }
}

export default EquityCurve;
