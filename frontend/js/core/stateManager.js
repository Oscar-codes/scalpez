/**
 * QuantPulse – State Manager (Centralizado)
 * ============================================
 * Store reactivo minimalista que mantiene el estado global de la app.
 *
 * PRINCIPIO: Single Source of Truth.
 * Todos los componentes leen de aquí. Nadie muta directamente.
 * Las mutaciones pasan por set() → que notifica automáticamente
 * via EventBus a los suscriptores de esa clave.
 *
 * CÓMO SE EVITA ESTADO INCONSISTENTE:
 *   - setState() es la ÚNICA vía de mutación.
 *   - Cada set() verifica si el valor realmente cambió (shallow compare).
 *   - Si no cambió, NO emite evento → evita re-renders innecesarios.
 *
 * CÓMO SE EVITA RE-RENDER INNECESARIO:
 *   - Los componentes se suscriben a claves específicas ('state:stats').
 *   - Solo reciben notificación si SU dato cambió.
 *   - Comparación shallow para primitivos, referencia para objetos.
 *
 * ESTRUCTURA DEL ESTADO:
 *   {
 *     currentSymbol:    'R_100',
 *     symbols:          ['stpRNG', 'R_100', 'R_75'],
 *     connectionStatus: 'disconnected' | 'connecting' | 'connected',
 *     candles:          { R_100: [...], stpRNG: [...], R_75: [...] },
 *     indicators:       { R_100: {...}, ... },
 *     activeSignal:     null | { symbol, signal_type, entry, ... },
 *     activeTrades:     { R_100: {...} | null, ... },
 *     tradeHistory:     [...],
 *     stats:            { global: {...}, by_symbol: {...} },
 *     lastTick:         { R_100: {...}, ... },
 *   }
 */

import EventBus from './eventBus.js';

const StateManager = (() => {
  // ── Estado inicial ──────────────────────────────────────────────
  const _state = {
    currentSymbol: 'R_100',
    symbols: ['stpRNG', 'R_100', 'R_75'],
    connectionStatus: 'disconnected',

    // Multi-timeframe
    activeTimeframe: '5m',
    availableTimeframes: ['5m', '15m', '30m', '1h'],

    // Datos de mercado por símbolo (candles del TF activo)
    candles: {},      // { symbol: Candle[] }  max 200 por símbolo
    indicators: {},   // { symbol: { ema_9, ema_21, rsi_14, timeframe, ... } }
    lastTick: {},     // { symbol: { quote, epoch } }

    // Señales y trades
    activeSignal: null,           // última señal emitida
    activeTrades: {},             // { symbol: trade | null }
    tradeHistory: [],             // trades cerrados (últimos 100)

    // Métricas cuantitativas
    stats: null,                  // { global: {...}, by_symbol: {...} }
  };

  /** Máximo de velas en memoria por símbolo */
  const MAX_CANDLES = 200;
  /** Máximo de trades en historial */
  const MAX_HISTORY = 100;

  // ── API Pública ─────────────────────────────────────────────────

  /**
   * Obtener valor del estado.
   * @param {string} key
   * @returns {*}
   */
  function get(key) {
    return _state[key];
  }

  /**
   * Obtener snapshot completo (read-only).
   * @returns {Object}
   */
  function getAll() {
    return { ..._state };
  }

  /**
   * Mutar estado y notificar suscriptores.
   * Solo emite si el valor realmente cambió.
   * @param {string} key
   * @param {*} value
   */
  function set(key, value) {
    if (_state[key] === value) return; // shallow compare → no re-render
    _state[key] = value;
    EventBus.emit(`state:${key}`, value);
  }

  // ── Mutaciones especializadas ───────────────────────────────────

  /**
   * Añadir vela cerrada al buffer del símbolo.
   * Limita a MAX_CANDLES (FIFO: elimina la más vieja si excede).
   * @param {Object} candle  { symbol, timestamp, open, high, low, close, ... }
   */
  function addCandle(candle) {
    const sym = candle.symbol;
    if (!_state.candles[sym]) _state.candles[sym] = [];

    const arr = _state.candles[sym];
    arr.push(candle);

    // FIFO: mantener máximo MAX_CANDLES
    if (arr.length > MAX_CANDLES) {
      arr.shift();
    }

    // Emitir evento específico para el símbolo actual
    if (sym === _state.currentSymbol) {
      EventBus.emit('state:candles', { symbol: sym, candles: arr });
    }
  }

  /**
   * Actualizar indicadores de un símbolo.
   * @param {Object} data  { symbol, ema_9, ema_21, rsi_14, ... }
   */
  function updateIndicators(data) {
    const sym = data.symbol;
    _state.indicators[sym] = data;

    if (sym === _state.currentSymbol) {
      EventBus.emit('state:indicators', data);
    }
  }

  /**
   * Actualizar último tick de un símbolo.
   * @param {Object} tick  { symbol, epoch, quote }
   */
  function updateTick(tick) {
    _state.lastTick[tick.symbol] = tick;
    EventBus.emit('state:tick', tick);
  }

  /**
   * Registrar nueva señal.
   * @param {Object} signal
   */
  function addSignal(signal) {
    _state.activeSignal = signal;
    EventBus.emit('state:activeSignal', signal);
  }

  /**
   * Registrar trade abierto.
   * @param {Object} trade
   */
  function addTradeOpened(trade) {
    _state.activeTrades[trade.symbol] = trade;
    EventBus.emit('state:activeTrades', { ..._state.activeTrades });
  }

  /**
   * Registrar trade cerrado → mover de activos a historial.
   * @param {Object} trade
   */
  function addTradeClosed(trade) {
    // Remover de activos
    _state.activeTrades[trade.symbol] = null;

    // Añadir al historial (más reciente primero)
    _state.tradeHistory.unshift(trade);
    if (_state.tradeHistory.length > MAX_HISTORY) {
      _state.tradeHistory.pop();
    }

    EventBus.emit('state:activeTrades', { ..._state.activeTrades });
    EventBus.emit('state:tradeHistory', _state.tradeHistory);
  }

  /**
   * Actualizar métricas de performance.
   * @param {Object} stats  { global: {...}, by_symbol: {...} }
   */
  function updateStats(stats) {
    _state.stats = stats;
    EventBus.emit('state:stats', stats);
  }

  /**
   * Cambiar timeframe activo.
   * Limpia candles/indicators cacheados y notifica componentes.
   * @param {string} tf  e.g. '5m', '15m', '30m', '1h'
   */
  function setActiveTimeframe(tf) {
    if (tf === _state.activeTimeframe) return;
    if (!_state.availableTimeframes.includes(tf)) return;
    _state.activeTimeframe = tf;
    // Limpiar datos del TF anterior para forzar refetch
    _state.candles = {};
    _state.indicators = {};
    EventBus.emit('state:activeTimeframe', tf);
  }

  return Object.freeze({
    get,
    getAll,
    set,
    addCandle,
    updateIndicators,
    updateTick,
    addSignal,
    addTradeOpened,
    addTradeClosed,
    updateStats,
    setActiveTimeframe,
    MAX_CANDLES,
  });
})();

export default StateManager;
