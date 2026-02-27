/**
 * QuantPulse – Chart Adapter
 * ============================
 * Utilidades compartidas para gráficos de canvas.
 */

export const CHART_COLORS = Object.freeze({
  bg:             '#0d1117',
  grid:           '#1b2028',
  gridText:       '#555e6a',
  bullish:        '#26a69a',
  bearish:        '#ef5350',
  wick:           '#555e6a',
  ema9:           '#42a5f5',
  ema21:          '#ffa726',
  rsiLine:        '#ab47bc',
  rsiOverBought:  'rgba(239,83,80,0.15)',
  rsiOverSold:    'rgba(38,166,154,0.15)',
  rsiZone:        '#333',
  signalBuy:      '#26a69a',
  signalSell:     '#ef5350',
  tpLine:         '#26a69a',
  slLine:         '#ef5350',
  crosshair:      'rgba(255,255,255,0.1)',
  lastPrice:      '#ffffff',
});

/**
 * Formatear precio según precisión.
 * @param {number} price
 * @param {number} decimals
 * @returns {string}
 */
export function formatPrice(price, decimals = 2) {
  if (price === null || price === undefined || isNaN(price)) return '--';
  
  // Determinar decimales según magnitud
  if (price > 1000) {
    return price.toFixed(decimals);
  } else if (price > 1) {
    return price.toFixed(Math.max(2, decimals));
  } else {
    return price.toFixed(5);
  }
}

/**
 * Debounce function.
 * @param {Function} fn
 * @param {number} delay
 * @returns {Function}
 */
export function debounce(fn, delay) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * Obtener escala de precios para un conjunto de velas.
 * @param {Array} candles
 * @param {number} margin - Porcentaje de margen (ej: 0.02 = 2%)
 * @returns {{ min: number, max: number, range: number }}
 */
export function getPriceScale(candles, margin = 0.02) {
  if (!candles || candles.length === 0) {
    return { min: 0, max: 100, range: 100 };
  }

  let min = Infinity;
  let max = -Infinity;

  for (const c of candles) {
    if (c.low < min) min = c.low;
    if (c.high > max) max = c.high;
  }

  const range = max - min || 1;
  min -= range * margin;
  max += range * margin;

  return { min, max, range: max - min };
}

/**
 * Crear función de mapeo precio → Y.
 * @param {number} minPrice
 * @param {number} maxPrice
 * @param {number} height - Altura total del área
 * @param {number} padTop
 * @param {number} padBottom
 * @returns {Function}
 */
export function createPriceToY(minPrice, maxPrice, height, padTop = 10, padBottom = 4) {
  const drawHeight = height - padTop - padBottom;
  const range = maxPrice - minPrice || 1;
  
  return (price) => {
    return padTop + (1 - (price - minPrice) / range) * drawHeight;
  };
}

/**
 * Dibujar grid de precios.
 * @param {CanvasRenderingContext2D} ctx
 * @param {Object} options
 */
export function drawPriceGrid(ctx, options) {
  const {
    width,
    height,
    padLeft,
    padRight,
    minPrice,
    maxPrice,
    priceToY,
    steps = 6,
    color = CHART_COLORS.grid,
    textColor = CHART_COLORS.gridText,
  } = options;

  const step = (maxPrice - minPrice) / steps;
  ctx.strokeStyle = color;
  ctx.lineWidth = 0.5;
  ctx.fillStyle = textColor;
  ctx.font = '10px monospace';
  ctx.textAlign = 'right';

  for (let i = 0; i <= steps; i++) {
    const price = minPrice + step * i;
    const y = priceToY(price);
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();
  }
}

/**
 * Dibujar escala lateral de precios.
 * @param {CanvasRenderingContext2D} ctx
 * @param {Object} options
 */
export function drawPriceScale(ctx, options) {
  const {
    width,
    padRight,
    minPrice,
    maxPrice,
    priceToY,
    steps = 6,
    textColor = CHART_COLORS.gridText,
  } = options;

  const step = (maxPrice - minPrice) / steps;
  ctx.fillStyle = textColor;
  ctx.font = '10px monospace';
  ctx.textAlign = 'left';

  for (let i = 0; i <= steps; i++) {
    const price = minPrice + step * i;
    const y = priceToY(price);
    ctx.fillText(formatPrice(price), width - padRight + 4, y + 3);
  }
}

/**
 * Dibujar línea horizontal con label.
 * @param {CanvasRenderingContext2D} ctx
 * @param {Object} options
 */
export function drawHorizontalLine(ctx, options) {
  const {
    price,
    color,
    label,
    width,
    padLeft,
    padRight,
    priceToY,
    minPrice,
    maxPrice,
    dashed = true,
  } = options;

  if (price === null || price === undefined) return;
  if (price < minPrice || price > maxPrice) return;

  const y = priceToY(price);

  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  if (dashed) ctx.setLineDash([4, 4]);
  
  ctx.beginPath();
  ctx.moveTo(padLeft, y);
  ctx.lineTo(width - padRight, y);
  ctx.stroke();
  
  if (dashed) ctx.setLineDash([]);

  // Label
  if (label) {
    ctx.fillStyle = color;
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'right';
    ctx.fillText(label, width - padRight - 4, y - 4);
  }
}

export default {
  CHART_COLORS,
  formatPrice,
  debounce,
  getPriceScale,
  createPriceToY,
  drawPriceGrid,
  drawPriceScale,
  drawHorizontalLine,
};
