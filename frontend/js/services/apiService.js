/**
 * QuantPulse – API Service (REST)
 * =================================
 * Cliente HTTP para endpoints REST del backend.
 *
 * Se usa para:
 *   - Carga inicial de datos (candles históricas, stats, trades)
 *   - Fetch bajo demanda que no llega por WebSocket
 *
 * NO SE USA PARA:
 *   - Datos en tiempo real (eso es WebSocket)
 *   - Polling (el WS reemplaza polling)
 */

const ApiService = (() => {
  const _baseUrl = '';  // mismo host/port que sirve el frontend

  /**
   * Fetch genérico con manejo de errores (GET).
   * @param {string} path  e.g. '/api/stats'
   * @returns {Promise<Object|null>}
   */
  async function _fetch(path) {
    try {
      const res = await fetch(`${_baseUrl}${path}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error(`[API] Error fetching ${path}:`, err);
      return null;
    }
  }

  /**
   * POST genérico con JSON body.
   * @param {string} path
   * @param {Object} body
   * @returns {Promise<Object|null>}
   */
  async function _post(path, body) {
    try {
      const res = await fetch(`${_baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error(`[API] Error posting ${path}:`, err);
      return null;
    }
  }

  /** Obtener últimas N velas de un símbolo (base 5s — legacy) */
  async function getCandles(symbol, count = 200) {
    return _fetch(`/api/candles/${symbol}?count=${count}`);
  }

  /** Obtener velas de un símbolo para un timeframe específico */
  async function getTfCandles(symbol, timeframe, count = 200) {
    return _fetch(`/api/candles/${symbol}/${timeframe}?count=${count}`);
  }

  /** Obtener indicadores de un símbolo (opcionalmente por timeframe) */
  async function getIndicators(symbol, timeframe = null) {
    const qs = timeframe ? `?timeframe=${timeframe}` : '';
    return _fetch(`/api/indicators/${symbol}${qs}`);
  }

  /** Obtener todos los indicadores */
  async function getAllIndicators() {
    return _fetch('/api/indicators');
  }

  /** Obtener timeframe activo y disponibles */
  async function getTimeframe() {
    return _fetch('/api/timeframe');
  }

  /** Cambiar timeframe activo en el servidor */
  async function setTimeframe(tf) {
    return _post('/api/timeframe', { timeframe: tf });
  }

  /** Obtener señales recientes */
  async function getRecentSignals(symbol = null, count = 20) {
    const qs = symbol ? `?symbol=${symbol}&count=${count}` : `?count=${count}`;
    return _fetch(`/api/signals/recent${qs}`);
  }

  /** Obtener stats del signal engine */
  async function getSignalStats() {
    return _fetch('/api/signals/stats');
  }

  /** Obtener métricas de performance globales + por símbolo */
  async function getStats() {
    return _fetch('/api/stats');
  }

  /** Obtener métricas de un símbolo */
  async function getStatsBySymbol(symbol) {
    return _fetch(`/api/stats/${symbol}`);
  }

  /** Obtener trades activos */
  async function getActiveTrades() {
    return _fetch('/api/trades/active');
  }

  /** Obtener historial de trades */
  async function getTradeHistory(symbol = null, count = 50) {
    const qs = symbol ? `?symbol=${symbol}&count=${count}` : `?count=${count}`;
    return _fetch(`/api/trades/history${qs}`);
  }

  /** Health check */
  async function health() {
    return _fetch('/api/health');
  }

  /** Estado completo del sistema */
  async function getStatus() {
    return _fetch('/api/status');
  }

  return Object.freeze({
    getCandles,
    getTfCandles,
    getIndicators,
    getAllIndicators,
    getTimeframe,
    setTimeframe,
    getRecentSignals,
    getSignalStats,
    getStats,
    getStatsBySymbol,
    getActiveTrades,
    getTradeHistory,
    health,
    getStatus,
  });
})();

export default ApiService;
