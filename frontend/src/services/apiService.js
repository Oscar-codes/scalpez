/**
 * QuantPulse – API Service
 * ==========================
 * Cliente HTTP centralizado para endpoints REST.
 *
 * PRINCIPIOS:
 *   - Ningún componente llama a fetch() directamente
 *   - Manejo de errores centralizado
 *   - Actualiza UIState.loading automáticamente
 *   - Retorna datos ya parseados
 *
 * USO:
 *   const candles = await ApiService.getCandles('R_100', '5m');
 */

import CONFIG from '../core/config.js';
import { UIState } from '../core/state/index.js';

class ApiServiceClass {
  constructor() {
    this._baseUrl = CONFIG.API_BASE_URL;
  }

  /**
   * Request GET genérico.
   * @param {string} path
   * @param {Object} [options]
   * @returns {Promise<Object|null>}
   * @private
   */
  async _get(path, options = {}) {
    const { loadingKey, silent = false } = options;
    
    if (loadingKey) UIState.setLoading(loadingKey, true);
    
    try {
      const response = await fetch(`${this._baseUrl}${path}`);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      if (!silent) {
        console.error(`[API] Error GET ${path}:`, error);
        UIState.setError(`Error al obtener datos: ${error.message}`);
      }
      return null;
    } finally {
      if (loadingKey) UIState.setLoading(loadingKey, false);
    }
  }

  /**
   * Request POST genérico.
   * @param {string} path
   * @param {Object} body
   * @param {Object} [options]
   * @returns {Promise<Object|null>}
   * @private
   */
  async _post(path, body, options = {}) {
    const { loadingKey, silent = false } = options;
    
    if (loadingKey) UIState.setLoading(loadingKey, true);
    
    try {
      const response = await fetch(`${this._baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      if (!silent) {
        console.error(`[API] Error POST ${path}:`, error);
        UIState.setError(`Error en solicitud: ${error.message}`);
      }
      return null;
    } finally {
      if (loadingKey) UIState.setLoading(loadingKey, false);
    }
  }

  // ══════════════════════════════════════════════════════════════
  //  MARKET DATA
  // ══════════════════════════════════════════════════════════════

  /**
   * Obtener velas para un símbolo y timeframe.
   * @param {string} symbol
   * @param {string} timeframe
   * @param {number} [count=200]
   * @returns {Promise<Array|null>}
   */
  async getCandles(symbol, timeframe, count = 200) {
    return this._get(
      `/api/candles/${symbol}/${timeframe}?count=${count}`,
      { loadingKey: 'candles' }
    );
  }

  /**
   * Obtener indicadores de un símbolo.
   * @param {string} symbol
   * @param {string} [timeframe]
   * @returns {Promise<Object|null>}
   */
  async getIndicators(symbol, timeframe = null) {
    const qs = timeframe ? `?timeframe=${timeframe}` : '';
    return this._get(`/api/indicators/${symbol}${qs}`);
  }

  /**
   * Obtener todos los indicadores.
   * @returns {Promise<Object|null>}
   */
  async getAllIndicators() {
    return this._get('/api/indicators');
  }

  // ══════════════════════════════════════════════════════════════
  //  TIMEFRAME
  // ══════════════════════════════════════════════════════════════

  /**
   * Obtener timeframe activo.
   * @returns {Promise<Object|null>}
   */
  async getTimeframe() {
    return this._get('/api/timeframe');
  }

  /**
   * Cambiar timeframe activo.
   * @param {string} timeframe
   * @returns {Promise<Object|null>}
   */
  async setTimeframe(timeframe) {
    return this._post('/api/timeframe', { timeframe });
  }

  // ══════════════════════════════════════════════════════════════
  //  SIGNALS
  // ══════════════════════════════════════════════════════════════

  /**
   * Obtener señales recientes.
   * @param {string} [symbol]
   * @param {number} [count=20]
   * @returns {Promise<Array|null>}
   */
  async getRecentSignals(symbol = null, count = 20) {
    const params = new URLSearchParams({ count: count.toString() });
    if (symbol) params.append('symbol', symbol);
    return this._get(`/api/signals/recent?${params}`);
  }

  /**
   * Obtener estadísticas del signal engine.
   * @returns {Promise<Object|null>}
   */
  async getSignalStats() {
    return this._get('/api/signals/stats');
  }

  // ══════════════════════════════════════════════════════════════
  //  TRADES & STATS
  // ══════════════════════════════════════════════════════════════

  /**
   * Obtener métricas de performance.
   * @returns {Promise<Object|null>}
   */
  async getStats() {
    return this._get('/api/stats', { loadingKey: 'stats' });
  }

  /**
   * Obtener historial de trades.
   * @param {number} [count=100]
   * @returns {Promise<Array|null>}
   */
  async getTradeHistory(count = 100) {
    return this._get(`/api/trades/history?count=${count}`, { loadingKey: 'trades' });
  }

  /**
   * Obtener trades activos.
   * @returns {Promise<Object|null>}
   */
  async getActiveTrades() {
    return this._get('/api/trades/active');
  }

  // ══════════════════════════════════════════════════════════════
  //  ML (Futuro)
  // ══════════════════════════════════════════════════════════════

  /**
   * Obtener predicción ML.
   * @param {string} symbol
   * @returns {Promise<Object|null>}
   */
  async getMLPrediction(symbol) {
    return this._get(`/api/ml/predict/${symbol}`);
  }

  /**
   * Obtener estado del modelo ML.
   * @returns {Promise<Object|null>}
   */
  async getMLStatus() {
    return this._get('/api/ml/status');
  }

  // ══════════════════════════════════════════════════════════════
  //  SETTINGS
  // ══════════════════════════════════════════════════════════════

  /**
   * Actualizar configuración del engine.
   * @param {Object} settings
   * @returns {Promise<Object|null>}
   */
  async updateSettings(settings) {
    return this._post('/api/settings', settings, { loadingKey: 'settings' });
  }

  /**
   * Obtener configuración actual.
   * @returns {Promise<Object|null>}
   */
  async getSettings() {
    return this._get('/api/settings');
  }
}

// Singleton
const ApiService = new ApiServiceClass();

export { ApiService, ApiServiceClass };
export default ApiService;
