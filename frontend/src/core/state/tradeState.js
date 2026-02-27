/**
 * QuantPulse – Trade State Slice
 * ================================
 * Estado relacionado con señales y trades.
 *
 * RESPONSABILIDADES:
 *   - Señal activa actual
 *   - Trades activos por símbolo
 *   - Historial de trades cerrados
 *   - Estadísticas de performance
 */

import Store from './store.js';
import CONFIG from '../config.js';

// ── Estado Inicial ──
const initialState = {
  // Señales
  activeSignal: null,           // última señal emitida
  recentSignals: [],            // últimas N señales (para historial visual)
  
  // Trades
  activeTradesBySymbol: {},     // { R_100: trade | null, ... }
  tradeHistory: [],             // trades cerrados (FIFO max 100)
  
  // Stats
  stats: null,                  // { global: {...}, bySymbol: {...} }
  lastStatsUpdate: null,        // timestamp de última actualización
};

// ── Registrar Slice ──
Store.registerSlice('trading', initialState);

// ── Actions ──

const TradeState = {
  /**
   * Registrar nueva señal.
   * @param {Object} signal
   */
  addSignal(signal) {
    Store.setState('trading.activeSignal', signal);
    
    // También añadir a recientes
    const recent = Store.getState('trading.recentSignals') || [];
    const newRecent = [signal, ...recent].slice(0, CONFIG.MAX_VISIBLE_SIGNALS);
    Store.setState('trading.recentSignals', newRecent);
  },

  /**
   * Trade abierto.
   * @param {Object} trade
   */
  addTradeOpened(trade) {
    const currentTrades = Store.getState('trading.activeTradesBySymbol') || {};
    Store.setState('trading.activeTradesBySymbol', {
      ...currentTrades,
      [trade.symbol]: trade,
    });
  },

  /**
   * Trade cerrado.
   * @param {Object} trade
   */
  addTradeClosed(trade) {
    const currentTrades = Store.getState('trading.activeTradesBySymbol') || {};
    const history = Store.getState('trading.tradeHistory') || [];
    
    Store.batch(() => {
      // Remover de activos
      Store.setState('trading.activeTradesBySymbol', {
        ...currentTrades,
        [trade.symbol]: null,
      });
      
      // Añadir a historial (FIFO)
      const newHistory = [trade, ...history].slice(0, CONFIG.MAX_TRADE_HISTORY);
      Store.setState('trading.tradeHistory', newHistory);
    });
  },

  /**
   * Actualizar stats.
   * @param {Object} stats
   */
  setStats(stats) {
    Store.batch(() => {
      Store.setState('trading.stats', stats);
      Store.setState('trading.lastStatsUpdate', Date.now());
    });
  },

  /**
   * Obtener trade activo para un símbolo.
   * @param {string} symbol
   * @returns {Object|null}
   */
  getActiveTrade(symbol) {
    const trades = Store.getState('trading.activeTradesBySymbol') || {};
    return trades[symbol] || null;
  },

  /**
   * Obtener trade activo del símbolo actual.
   * @returns {Object|null}
   */
  getCurrentActiveTrade() {
    const symbol = Store.getState('market.currentSymbol');
    return this.getActiveTrade(symbol);
  },

  /**
   * Verificar si hay trade activo.
   * @param {string} [symbol] - Si no se pasa, revisa todos
   * @returns {boolean}
   */
  hasActiveTrade(symbol) {
    const trades = Store.getState('trading.activeTradesBySymbol') || {};
    if (symbol) {
      return !!trades[symbol];
    }
    return Object.values(trades).some(t => t !== null);
  },

  /**
   * Obtener estadísticas globales.
   * @returns {Object|null}
   */
  getGlobalStats() {
    const stats = Store.getState('trading.stats');
    return stats?.global || null;
  },

  /**
   * Obtener estadísticas por símbolo.
   * @param {string} symbol
   * @returns {Object|null}
   */
  getSymbolStats(symbol) {
    const stats = Store.getState('trading.stats');
    return stats?.bySymbol?.[symbol] || null;
  },

  /**
   * Clear all trades (reset).
   */
  clearAll() {
    Store.batch(() => {
      Store.setState('trading.activeSignal', null);
      Store.setState('trading.recentSignals', []);
      Store.setState('trading.activeTradesBySymbol', {});
      Store.setState('trading.tradeHistory', []);
    });
  },
};

export { TradeState, initialState as tradingInitialState };
export default TradeState;
