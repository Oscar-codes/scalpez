/**
 * QuantPulse – Main Application Entry Point
 * =============================================
 * Punto de entrada principal de la aplicación.
 * Inicializa el Store, los servicios y el dashboard.
 */

// Core
import { Store } from './core/state/store.js';
import { MarketState } from './core/state/marketState.js';
import { TradeState } from './core/state/tradeState.js';
import { UIState } from './core/state/uiState.js';
import { CONFIG } from './core/config.js';

// Dashboard
import { Dashboard } from './modules/dashboard/index.js';

/**
 * Inicializar la aplicación.
 */
async function initApp() {
  console.log('[App] QuantPulse v1.0 starting...');
  
  // 1. Registrar slices del Store
  Store.registerSlice('market', {
    currentSymbol: CONFIG.DEFAULT_SYMBOLS[0],
    symbols: CONFIG.DEFAULT_SYMBOLS,
    candles: {},
    indicators: {},
    lastTick: null,
    connected: false,
  });

  Store.registerSlice('trading', {
    signals: [],
    openTrades: [],
    closedTrades: [],
    stats: null,
  });

  Store.registerSlice('ui', {
    currentView: 'dashboard',
    currentTimeframe: CONFIG.DEFAULT_TIMEFRAME,
    sidebarCollapsed: false,
    theme: 'dark',
    loading: false,
    notifications: [],
    audioMuted: false,
  });

  // 2. Inicializar Dashboard
  await Dashboard.init();
  
  console.log('[App] Ready');
}

// Esperar a que el DOM esté listo
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

// Hot reload support (desarrollo)
if (import.meta.hot) {
  import.meta.hot.accept();
}
