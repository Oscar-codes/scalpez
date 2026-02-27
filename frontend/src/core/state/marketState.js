/**
 * QuantPulse – Market State Slice
 * =================================
 * Estado relacionado con datos de mercado en tiempo real.
 *
 * RESPONSABILIDADES:
 *   - Símbolo activo
 *   - Timeframe activo
 *   - Velas por símbolo
 *   - Indicadores por símbolo
 *   - Último tick por símbolo
 */

import Store from './store.js';
import CONFIG from '../config.js';

// ── Estado Inicial ──
const initialState = {
  currentSymbol: CONFIG.DEFAULT_SYMBOL,
  currentTimeframe: CONFIG.DEFAULT_TIMEFRAME,
  availableSymbols: CONFIG.AVAILABLE_SYMBOLS,
  availableTimeframes: CONFIG.AVAILABLE_TIMEFRAMES,
  connectionStatus: 'disconnected',  // 'disconnected' | 'connecting' | 'connected'
  
  // Datos por símbolo
  candlesBySymbol: {},      // { R_100: Candle[], ... }
  indicatorsBySymbol: {},   // { R_100: { ema_9, ema_21, rsi_14, ... }, ... }
  lastTickBySymbol: {},     // { R_100: { quote, epoch }, ... }
};

// ── Registrar Slice ──
Store.registerSlice('market', initialState);

// ── Actions (funciones puras que modifican estado) ──

const MarketState = {
  /**
   * Cambiar símbolo activo.
   * @param {string} symbol
   */
  setCurrentSymbol(symbol) {
    if (!CONFIG.AVAILABLE_SYMBOLS.includes(symbol)) {
      console.warn(`[MarketState] Símbolo inválido: ${symbol}`);
      return;
    }
    Store.setState('market.currentSymbol', symbol);
  },

  /**
   * Cambiar timeframe activo.
   * @param {string} timeframe
   */
  setTimeframe(timeframe) {
    if (!CONFIG.AVAILABLE_TIMEFRAMES.includes(timeframe)) {
      console.warn(`[MarketState] Timeframe inválido: ${timeframe}`);
      return;
    }
    Store.setState('market.currentTimeframe', timeframe);
  },

  /**
   * Actualizar estado de conexión.
   * @param {'disconnected'|'connecting'|'connected'} status
   */
  setConnectionStatus(status) {
    Store.setState('market.connectionStatus', status);
  },

  /**
   * Añadir vela cerrada.
   * @param {Object} candle - { symbol, timestamp, open, high, low, close, ... }
   */
  addCandle(candle) {
    const symbol = candle.symbol;
    const currentCandles = Store.getState('market.candlesBySymbol') || {};
    const symbolCandles = currentCandles[symbol] || [];
    
    // Añadir nueva vela
    const newCandles = [...symbolCandles, candle];
    
    // FIFO: mantener máximo MAX_CANDLES
    if (newCandles.length > CONFIG.MAX_CANDLES) {
      newCandles.shift();
    }
    
    Store.setState('market.candlesBySymbol', {
      ...currentCandles,
      [symbol]: newCandles,
    });
  },

  /**
   * Establecer velas iniciales (carga REST).
   * @param {string} symbol
   * @param {Array} candles
   */
  setCandles(symbol, candles) {
    const currentCandles = Store.getState('market.candlesBySymbol') || {};
    Store.setState('market.candlesBySymbol', {
      ...currentCandles,
      [symbol]: candles.slice(-CONFIG.MAX_CANDLES),
    });
  },

  /**
   * Actualizar indicadores de un símbolo.
   * @param {Object} data - { symbol, ema_9, ema_21, rsi_14, ... }
   */
  updateIndicators(data) {
    const currentIndicators = Store.getState('market.indicatorsBySymbol') || {};
    Store.setState('market.indicatorsBySymbol', {
      ...currentIndicators,
      [data.symbol]: data,
    });
  },

  /**
   * Actualizar último tick.
   * @param {Object} tick - { symbol, quote, epoch }
   */
  updateTick(tick) {
    const currentTicks = Store.getState('market.lastTickBySymbol') || {};
    Store.setState('market.lastTickBySymbol', {
      ...currentTicks,
      [tick.symbol]: tick,
    });
  },

  /**
   * Obtener velas del símbolo actual.
   * @returns {Array}
   */
  getCurrentCandles() {
    const symbol = Store.getState('market.currentSymbol');
    const candles = Store.getState('market.candlesBySymbol') || {};
    return candles[symbol] || [];
  },

  /**
   * Obtener indicadores del símbolo actual.
   * @returns {Object|null}
   */
  getCurrentIndicators() {
    const symbol = Store.getState('market.currentSymbol');
    const indicators = Store.getState('market.indicatorsBySymbol') || {};
    return indicators[symbol] || null;
  },

  /**
   * Limpiar datos de un símbolo (al cambiar TF, por ejemplo).
   * @param {string} symbol
   */
  clearSymbolData(symbol) {
    const candles = Store.getState('market.candlesBySymbol') || {};
    const indicators = Store.getState('market.indicatorsBySymbol') || {};
    
    Store.batch(() => {
      Store.setState('market.candlesBySymbol', {
        ...candles,
        [symbol]: [],
      });
      Store.setState('market.indicatorsBySymbol', {
        ...indicators,
        [symbol]: null,
      });
    });
  },
};

export { MarketState, initialState as marketInitialState };
export default MarketState;
