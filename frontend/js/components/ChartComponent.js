/**
 * QuantPulse – Chart Component (Candlestick + EMA + RSI)
 * ========================================================
 * Gráfico principal de candlestick en tiempo real usando Canvas 2D.
 *
 * RESPONSABILIDADES:
 *   1. Dibujar candlestick chart (máximo 200 velas)
 *   2. Overlays: EMA 9 (azul), EMA 21 (naranja)
 *   3. Subpanel: RSI 14 con zonas oversold/overbought
 *   4. Marcar señales BUY/SELL sobre el gráfico
 *   5. Marcar TP/SL si hay trade activo
 *   6. Actualizar en tiempo real sin redibujar todo
 *
 * OPTIMIZACIÓN DE RENDERIZADO:
 *   - Solo re-dibuja cuando llega vela nueva o cambio de símbolo.
 *   - NO redibuja en cada tick (innecesario para candlestick).
 *   - Usa requestAnimationFrame para sincronizar con el display.
 *   - Canvas 2D es más performante que SVG para >100 elementos.
 *   - Se mantiene un buffer de 200 velas máximo por símbolo.
 *
 * CÓMO SE EVITA MEMORY LEAK:
 *   - Al cambiar de símbolo no se crean nuevos canvas.
 *   - Se reutiliza el mismo context2D.
 *   - No hay event listeners acumulados.
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const ChartComponent = (() => {
  /** @type {HTMLCanvasElement|null} */
  let _canvas = null;
  /** @type {CanvasRenderingContext2D|null} */
  let _ctx = null;

  /** Cache de datos ya preparados para render rápido */
  let _cachedCandles = [];
  let _cachedIndicators = [];  // { ema_9, ema_21, rsi_14 } por vela
  let _rsiValues = [];

  /** Señales a marcar en el gráfico */
  let _signals = [];

  /** Trade activo actual (para TP/SL lines) */
  let _activeTrade = null;

  /** RAF id para cancelar si es necesario */
  let _rafId = null;

  /** Flag para agrupar múltiples updates en un solo frame */
  let _dirty = false;

  // ── Constantes de diseño ──────────────────────────────────────
  const COLORS = {
    bg:             '#0d1117',
    grid:           '#1b2028',
    gridText:       '#555e6a',
    bullish:        '#26a69a',   // verde suave
    bearish:        '#ef5350',   // rojo suave
    wick:           '#555e6a',
    ema9:           '#42a5f5',   // azul
    ema21:          '#ffa726',   // naranja
    rsiLine:        '#ab47bc',   // morado
    rsiOverBought:  'rgba(239,83,80,0.15)',
    rsiOverSold:    'rgba(38,166,154,0.15)',
    rsiZone:        '#333',
    signalBuy:      '#26a69a',
    signalSell:     '#ef5350',
    tpLine:         '#26a69a',
    slLine:         '#ef5350',
    crosshair:      'rgba(255,255,255,0.1)',
  };

  const RSI_PANEL_RATIO = 0.2;  // RSI ocupa 20% inferior

  // ── Inicialización ────────────────────────────────────────────

  function init(canvasId) {
    _canvas = document.getElementById(canvasId);
    if (!_canvas) return console.error('[Chart] Canvas no encontrado');

    _ctx = _canvas.getContext('2d');
    _resizeCanvas();

    window.addEventListener('resize', _debounce(_resizeCanvas, 200));
    _bindEvents();
  }

  function _resizeCanvas() {
    const parent = _canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    _canvas.width = parent.clientWidth * dpr;
    _canvas.height = parent.clientHeight * dpr;
    _canvas.style.width = parent.clientWidth + 'px';
    _canvas.style.height = parent.clientHeight + 'px';
    _ctx.scale(dpr, dpr);
    _scheduleRender();
  }

  // ── Suscripciones ─────────────────────────────────────────────

  function _bindEvents() {
    // Vela nueva → recalcular y redibujar
    EventBus.on('state:candles', ({ symbol, candles }) => {
      if (symbol !== StateManager.get('currentSymbol')) return;
      _cachedCandles = candles;
      _scheduleRender();
    });

    // Indicadores → se acumulan por vela
    EventBus.on('ws:indicators', (data) => {
      if (data.symbol !== StateManager.get('currentSymbol')) return;
      // Guardar indicadores para dibujar overlays
      _cachedIndicators.push({
        ema_9: data.ema_9,
        ema_21: data.ema_21,
      });
      if (data.rsi_14 !== null && data.rsi_14 !== undefined) {
        _rsiValues.push(data.rsi_14);
      }
      // Mantener sincronizado con candles
      const maxLen = StateManager.MAX_CANDLES;
      if (_cachedIndicators.length > maxLen) _cachedIndicators.shift();
      if (_rsiValues.length > maxLen) _rsiValues.shift();
      _scheduleRender();
    });

    // Señal nueva → marcar en gráfico
    EventBus.on('state:activeSignal', (signal) => {
      if (signal && signal.symbol === StateManager.get('currentSymbol')) {
        _signals.push(signal);
        // Limitar a últimas 20 señales visibles
        if (_signals.length > 20) _signals.shift();
        _scheduleRender();
      }
    });

    // Trade activo → dibujar TP/SL
    EventBus.on('state:activeTrades', (trades) => {
      const sym = StateManager.get('currentSymbol');
      _activeTrade = trades[sym] || null;
      _scheduleRender();
    });

    // Cambio de símbolo → resetear y recargar
    EventBus.on('state:currentSymbol', (symbol) => {
      _cachedCandles = StateManager.get('candles')[symbol] || [];
      _cachedIndicators = [];
      _rsiValues = [];
      _signals = [];
      _activeTrade = (StateManager.get('activeTrades') || {})[symbol] || null;
      _scheduleRender();
    });

    // Cambio de timeframe → resetear cache (app.js se encarga del refetch)
    EventBus.on('state:activeTimeframe', (tf) => {
      _cachedCandles = [];
      _cachedIndicators = [];
      _rsiValues = [];
      _signals = [];
      _scheduleRender();
      // Actualizar chart label
      const label = document.getElementById('chart-label');
      if (label) label.textContent = `Candlestick · ${tf}`;
    });
  }

  // ── Render Engine ─────────────────────────────────────────────

  function _scheduleRender() {
    if (_dirty) return; // ya hay un frame pendiente
    _dirty = true;
    _rafId = requestAnimationFrame(() => {
      _dirty = false;
      _draw();
    });
  }

  function _draw() {
    if (!_ctx || !_canvas) return;

    const W = _canvas.clientWidth;
    const H = _canvas.clientHeight;
    const rsiH = H * RSI_PANEL_RATIO;
    const chartH = H - rsiH;

    // Clear
    _ctx.clearRect(0, 0, W, H);

    // Background
    _ctx.fillStyle = COLORS.bg;
    _ctx.fillRect(0, 0, W, H);

    const candles = _cachedCandles;
    if (!candles || candles.length === 0) {
      _drawEmpty(W, H);
      return;
    }

    // Padding
    const padLeft = 8;
    const padRight = 60;  // espacio para escala de precio
    const padTop = 10;
    const padBot = 4;
    const chartW = W - padLeft - padRight;

    // ── Escala de precios ──────────────────────────────────────
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    for (const c of candles) {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
    }
    // Añadir margen 2%
    const priceRange = maxPrice - minPrice || 1;
    minPrice -= priceRange * 0.02;
    maxPrice += priceRange * 0.02;

    const priceToY = (price) => {
      return padTop + (1 - (price - minPrice) / (maxPrice - minPrice)) * (chartH - padTop - padBot);
    };

    // ── Dimensión de velas ─────────────────────────────────────
    const candleCount = candles.length;
    const candleSpacing = chartW / candleCount;
    const candleWidth = Math.max(1, candleSpacing * 0.65);

    // ── Grid horizontal (precios) ──────────────────────────────
    _drawPriceGrid(W, chartH, padLeft, padRight, padTop, padBot, minPrice, maxPrice, priceToY);

    // ── Dibujar velas ──────────────────────────────────────────
    for (let i = 0; i < candleCount; i++) {
      const c = candles[i];
      const x = padLeft + (i + 0.5) * candleSpacing;
      const isBull = c.close >= c.open;

      // Wick (sombra)
      _ctx.strokeStyle = isBull ? COLORS.bullish : COLORS.bearish;
      _ctx.lineWidth = 1;
      _ctx.beginPath();
      _ctx.moveTo(x, priceToY(c.high));
      _ctx.lineTo(x, priceToY(c.low));
      _ctx.stroke();

      // Body
      const bodyTop = priceToY(Math.max(c.open, c.close));
      const bodyBot = priceToY(Math.min(c.open, c.close));
      const bodyH = Math.max(1, bodyBot - bodyTop);

      _ctx.fillStyle = isBull ? COLORS.bullish : COLORS.bearish;
      _ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyH);
    }

    // ── EMA Overlays ───────────────────────────────────────────
    _drawEmaLine(_cachedIndicators, 'ema_9', COLORS.ema9, candleSpacing, padLeft, priceToY, candleCount);
    _drawEmaLine(_cachedIndicators, 'ema_21', COLORS.ema21, candleSpacing, padLeft, priceToY, candleCount);

    // ── Señales marcadas ───────────────────────────────────────
    _drawSignals(candles, candleSpacing, padLeft, priceToY);

    // ── TP / SL lines del trade activo ─────────────────────────
    if (_activeTrade) {
      _drawHorizontalLine(_activeTrade.take_profit, COLORS.tpLine, 'TP', W, padRight, priceToY, minPrice, maxPrice);
      _drawHorizontalLine(_activeTrade.stop_loss, COLORS.slLine, 'SL', W, padRight, priceToY, minPrice, maxPrice);
      _drawHorizontalLine(_activeTrade.entry_price || _activeTrade.signal_entry, '#888', 'E', W, padRight, priceToY, minPrice, maxPrice);
    }

    // ── Escala lateral de precio ───────────────────────────────
    _drawPriceScale(W, padRight, chartH, padTop, padBot, minPrice, maxPrice);

    // ── Last price line ────────────────────────────────────────
    if (candles.length > 0) {
      const lastClose = candles[candles.length - 1].close;
      const y = priceToY(lastClose);
      _ctx.setLineDash([2, 2]);
      _ctx.strokeStyle = '#fff';
      _ctx.lineWidth = 0.5;
      _ctx.beginPath();
      _ctx.moveTo(padLeft, y);
      _ctx.lineTo(W - padRight, y);
      _ctx.stroke();
      _ctx.setLineDash([]);

      // Price label en la escala lateral
      _ctx.fillStyle = '#fff';
      _ctx.font = '11px monospace';
      _ctx.textAlign = 'left';
      _ctx.fillText(_fmtPrice(lastClose), W - padRight + 4, y + 4);
    }

    // ── RSI Subpanel ───────────────────────────────────────────
    _drawRsi(W, H, rsiH, chartH, padLeft, padRight, candleSpacing, candleCount);
  }

  // ── Helpers de dibujo ─────────────────────────────────────────

  function _drawEmpty(W, H) {
    _ctx.fillStyle = '#555e6a';
    _ctx.font = '14px system-ui';
    _ctx.textAlign = 'center';
    _ctx.fillText('Esperando datos...', W / 2, H / 2);
  }

  function _drawPriceGrid(W, chartH, padL, padR, padT, padB, minP, maxP, toY) {
    const steps = 6;
    const step = (maxP - minP) / steps;
    _ctx.strokeStyle = COLORS.grid;
    _ctx.lineWidth = 0.5;
    _ctx.fillStyle = COLORS.gridText;
    _ctx.font = '10px monospace';
    _ctx.textAlign = 'right';

    for (let i = 0; i <= steps; i++) {
      const price = minP + step * i;
      const y = toY(price);
      _ctx.beginPath();
      _ctx.moveTo(padL, y);
      _ctx.lineTo(W - padR, y);
      _ctx.stroke();
    }
  }

  function _drawPriceScale(W, padR, chartH, padT, padB, minP, maxP) {
    const steps = 6;
    const step = (maxP - minP) / steps;
    _ctx.fillStyle = COLORS.gridText;
    _ctx.font = '10px monospace';
    _ctx.textAlign = 'left';
    const toY = (p) => padT + (1 - (p - minP) / (maxP - minP)) * (chartH - padT - padB);

    for (let i = 0; i <= steps; i++) {
      const price = minP + step * i;
      const y = toY(price);
      _ctx.fillText(_fmtPrice(price), W - padR + 4, y + 3);
    }
  }

  function _drawEmaLine(indicators, key, color, spacing, padL, toY, candleCount) {
    if (!indicators || indicators.length < 2) return;

    // Los indicadores están alineados con las últimas N velas
    const offset = candleCount - indicators.length;

    _ctx.strokeStyle = color;
    _ctx.lineWidth = 1.5;
    _ctx.beginPath();

    let started = false;
    for (let i = 0; i < indicators.length; i++) {
      const val = indicators[i][key];
      if (val === null || val === undefined) continue;

      const x = padL + (i + offset + 0.5) * spacing;
      const y = toY(val);

      if (!started) {
        _ctx.moveTo(x, y);
        started = true;
      } else {
        _ctx.lineTo(x, y);
      }
    }
    _ctx.stroke();
  }

  function _drawSignals(candles, spacing, padL, toY) {
    for (const sig of _signals) {
      // Encontrar la vela correspondiente por timestamp
      const idx = candles.findIndex(c =>
        Math.abs(c.timestamp - sig.candle_timestamp) < 10
      );
      if (idx < 0) continue;

      const x = padL + (idx + 0.5) * spacing;
      const isBuy = sig.signal_type === 'BUY';
      const y = toY(isBuy ? candles[idx].low : candles[idx].high);

      // Triángulo
      _ctx.fillStyle = isBuy ? COLORS.signalBuy : COLORS.signalSell;
      _ctx.beginPath();
      if (isBuy) {
        // Triángulo apuntando arriba debajo de la vela
        _ctx.moveTo(x, y + 4);
        _ctx.lineTo(x - 5, y + 14);
        _ctx.lineTo(x + 5, y + 14);
      } else {
        // Triángulo apuntando abajo encima de la vela
        _ctx.moveTo(x, y - 4);
        _ctx.lineTo(x - 5, y - 14);
        _ctx.lineTo(x + 5, y - 14);
      }
      _ctx.closePath();
      _ctx.fill();
    }
  }

  function _drawHorizontalLine(price, color, label, W, padR, toY, minP, maxP) {
    if (price < minP || price > maxP) return;
    const y = toY(price);

    _ctx.setLineDash([4, 3]);
    _ctx.strokeStyle = color;
    _ctx.lineWidth = 1;
    _ctx.beginPath();
    _ctx.moveTo(0, y);
    _ctx.lineTo(W - padR, y);
    _ctx.stroke();
    _ctx.setLineDash([]);

    // Label
    _ctx.fillStyle = color;
    _ctx.font = 'bold 10px monospace';
    _ctx.textAlign = 'left';
    _ctx.fillText(`${label} ${_fmtPrice(price)}`, W - padR + 4, y - 3);
  }

  function _drawRsi(W, H, rsiH, chartH, padL, padR, spacing, candleCount) {
    const rsiTop = chartH;
    const rsiPadTop = 14;
    const rsiInnerH = rsiH - rsiPadTop - 4;

    // Separator line
    _ctx.strokeStyle = COLORS.grid;
    _ctx.lineWidth = 1;
    _ctx.beginPath();
    _ctx.moveTo(0, rsiTop);
    _ctx.lineTo(W, rsiTop);
    _ctx.stroke();

    // Label
    _ctx.fillStyle = COLORS.gridText;
    _ctx.font = '10px monospace';
    _ctx.textAlign = 'left';
    _ctx.fillText('RSI 14', padL + 4, rsiTop + 12);

    // Overbought / Oversold zones
    const rsiToY = (rsi) => rsiTop + rsiPadTop + (1 - rsi / 100) * rsiInnerH;

    // Overbought zone (65-100)
    _ctx.fillStyle = COLORS.rsiOverBought;
    _ctx.fillRect(padL, rsiToY(100), W - padL - padR, rsiToY(65) - rsiToY(100));

    // Oversold zone (0-35)
    _ctx.fillStyle = COLORS.rsiOverSold;
    _ctx.fillRect(padL, rsiToY(35), W - padL - padR, rsiToY(0) - rsiToY(35));

    // 50 line
    _ctx.strokeStyle = COLORS.rsiZone;
    _ctx.lineWidth = 0.5;
    _ctx.setLineDash([2, 2]);
    _ctx.beginPath();
    _ctx.moveTo(padL, rsiToY(50));
    _ctx.lineTo(W - padR, rsiToY(50));
    _ctx.stroke();
    _ctx.setLineDash([]);

    // RSI scale labels
    _ctx.fillStyle = COLORS.gridText;
    _ctx.font = '9px monospace';
    _ctx.textAlign = 'left';
    [70, 50, 30].forEach(v => {
      _ctx.fillText(v.toString(), W - padR + 4, rsiToY(v) + 3);
    });

    // RSI line
    if (_rsiValues.length < 2) return;
    const offset = candleCount - _rsiValues.length;

    _ctx.strokeStyle = COLORS.rsiLine;
    _ctx.lineWidth = 1.5;
    _ctx.beginPath();

    let started = false;
    for (let i = 0; i < _rsiValues.length; i++) {
      const val = _rsiValues[i];
      if (val === null || val === undefined) continue;

      const x = padL + (i + offset + 0.5) * spacing;
      const y = rsiToY(val);

      if (!started) {
        _ctx.moveTo(x, y);
        started = true;
      } else {
        _ctx.lineTo(x, y);
      }
    }
    _ctx.stroke();
  }

  function _fmtPrice(price) {
    if (price > 10000) return price.toFixed(2);
    if (price > 100) return price.toFixed(2);
    return price.toFixed(5);
  }

  function _debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  return Object.freeze({ init });
})();

export default ChartComponent;
