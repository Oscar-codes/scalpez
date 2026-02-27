/**
 * QuantPulse – Equity Curve Component (mini chart)
 * ===================================================
 * Mini gráfico de equity curve usando Canvas.
 * Muestra la curva acumulada de PnL% trade a trade.
 *
 * OPTIMIZACIÓN:
 *   - Solo re-dibuja cuando cambian las stats.
 *   - Canvas ligero (no sobrecarga el DOM).
 *   - Se reutiliza el mismo context.
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const EquityCurve = (() => {
  let _canvas = null;
  let _ctx = null;

  function init(canvasId) {
    _canvas = document.getElementById(canvasId);
    if (!_canvas) return;
    _ctx = _canvas.getContext('2d');
    _resize();
    window.addEventListener('resize', _resize);
    _bindEvents();
  }

  function _resize() {
    if (!_canvas) return;
    const parent = _canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    _canvas.width = parent.clientWidth * dpr;
    _canvas.height = parent.clientHeight * dpr;
    _canvas.style.width = parent.clientWidth + 'px';
    _canvas.style.height = parent.clientHeight + 'px';
    _ctx.scale(dpr, dpr);
    _draw();
  }

  function _bindEvents() {
    EventBus.on('state:stats', () => _draw());
    EventBus.on('state:currentSymbol', () => _draw());
  }

  function _draw() {
    if (!_ctx || !_canvas) return;
    const W = _canvas.clientWidth;
    const H = _canvas.clientHeight;

    _ctx.clearRect(0, 0, W, H);
    _ctx.fillStyle = '#0d1117';
    _ctx.fillRect(0, 0, W, H);

    const stats = StateManager.get('stats');
    if (!stats) return;

    const sym = StateManager.get('currentSymbol');
    const data = (stats.by_symbol && stats.by_symbol[sym])
      ? stats.by_symbol[sym]
      : stats.global;

    const curve = data?.equity_curve;
    if (!curve || curve.length < 2) {
      _ctx.fillStyle = '#555e6a';
      _ctx.font = '11px system-ui';
      _ctx.textAlign = 'center';
      _ctx.fillText('Equity Curve', W / 2, H / 2);
      return;
    }

    // Include zero point at start
    const points = [0, ...curve];

    const padL = 4;
    const padR = 4;
    const padT = 8;
    const padB = 8;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

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

    const toX = (i) => padL + (i / (points.length - 1)) * chartW;
    const toY = (v) => padT + (1 - (v - minV) / totalRange) * chartH;

    // Zero line
    const zeroY = toY(0);
    _ctx.strokeStyle = '#333';
    _ctx.lineWidth = 0.5;
    _ctx.setLineDash([2, 2]);
    _ctx.beginPath();
    _ctx.moveTo(padL, zeroY);
    _ctx.lineTo(W - padR, zeroY);
    _ctx.stroke();
    _ctx.setLineDash([]);

    // Fill area
    _ctx.beginPath();
    _ctx.moveTo(toX(0), zeroY);
    for (let i = 0; i < points.length; i++) {
      _ctx.lineTo(toX(i), toY(points[i]));
    }
    _ctx.lineTo(toX(points.length - 1), zeroY);
    _ctx.closePath();

    const lastVal = points[points.length - 1];
    const gradient = _ctx.createLinearGradient(0, padT, 0, H - padB);
    if (lastVal >= 0) {
      gradient.addColorStop(0, 'rgba(38,166,154,0.3)');
      gradient.addColorStop(1, 'rgba(38,166,154,0.02)');
    } else {
      gradient.addColorStop(0, 'rgba(239,83,80,0.02)');
      gradient.addColorStop(1, 'rgba(239,83,80,0.3)');
    }
    _ctx.fillStyle = gradient;
    _ctx.fill();

    // Line
    _ctx.strokeStyle = lastVal >= 0 ? '#26a69a' : '#ef5350';
    _ctx.lineWidth = 1.5;
    _ctx.beginPath();
    for (let i = 0; i < points.length; i++) {
      const x = toX(i);
      const y = toY(points[i]);
      if (i === 0) _ctx.moveTo(x, y);
      else _ctx.lineTo(x, y);
    }
    _ctx.stroke();

    // End dot
    const lastX = toX(points.length - 1);
    const lastY = toY(lastVal);
    _ctx.fillStyle = lastVal >= 0 ? '#26a69a' : '#ef5350';
    _ctx.beginPath();
    _ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
    _ctx.fill();

    // Label
    _ctx.fillStyle = '#aaa';
    _ctx.font = '9px monospace';
    _ctx.textAlign = 'right';
    _ctx.fillText(`${lastVal >= 0 ? '+' : ''}${lastVal.toFixed(4)}%`, W - padR, padT + 10);
  }

  return Object.freeze({ init });
})();

export default EquityCurve;
