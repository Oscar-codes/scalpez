/**
 * QuantPulse – Frontend Configuration
 * =====================================
 * Configuración centralizada de la aplicación.
 * 
 * PRINCIPIO: Single Source of Configuration.
 * Todos los valores configurables están aquí.
 */

export const CONFIG = Object.freeze({
  // ── API & WebSocket ──
  API_BASE_URL: '',  // mismo host que sirve el frontend
  WS_PATH: '/ws/market',
  
  // ── Timeouts & Intervals ──
  STATS_POLL_INTERVAL: 15_000,     // fetch stats cada 15s
  WS_RECONNECT_INITIAL: 1_000,     // 1s inicial
  WS_RECONNECT_MAX: 30_000,        // 30s máximo
  
  // ── Data Limits ──
  MAX_CANDLES: 200,
  MAX_TRADE_HISTORY: 100,
  MAX_VISIBLE_SIGNALS: 20,
  
  // ── Default Values ──
  DEFAULT_SYMBOLS: ['R_100', 'R_10', 'R_75', 'stpRNG'],
  DEFAULT_TIMEFRAME: 5,  // segundos
  
  // ── Timeframes disponibles ──
  TIMEFRAMES: [
    { value: 5,   label: '5s' },
    { value: 15,  label: '15s' },
    { value: 30,  label: '30s' },
    { value: 60,  label: '1m' },
    { value: 300, label: '5m' },
  ],
  
  // ── Trade Settings (sensible defaults) ──
  DEFAULT_RR_RATIO: 2.0,      // Risk:Reward 1:2
  RR_OPTIONS: [1, 1.5, 2, 2.5, 3],
  TRADE_EXPIRY_MINUTES: 30,
  
  // ── Indicator Defaults ──
  EMA_FAST: 9,
  EMA_SLOW: 21,
  RSI_PERIOD: 14,
  RSI_OVERBOUGHT: 70,
  RSI_OVERSOLD: 30,
  
  // ── UI ──
  CHART_UPDATE_DEBOUNCE: 50,
  RESIZE_DEBOUNCE: 200,
  
  // ── Routes (para futuro router) ──
  ROUTES: {
    DASHBOARD: '/',
    ANALYTICS: '/analytics',
    SETTINGS: '/settings',
  },
});

export default CONFIG;
