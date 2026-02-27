/**
 * QuantPulse – Dashboard Controller
 * ====================================
 * Orquestador del dashboard que inicializa y coordina todos los módulos.
 */

import { Store } from '../../core/state/store.js';
import { EventBus } from '../../core/eventBus.js';
import { CONFIG } from '../../core/config.js';

// Services
import { ApiService } from '../../services/apiService.js';
import { WebSocketService } from '../../services/websocketService.js';
import { AudioService } from '../../services/audioService.js';

// Modules
import { ChartComponent } from '../charts/ChartComponent.js';
import { SymbolSelector, TimeframeSelector, SignalPanel, TradeTable } from '../trading/index.js';
import { StatsPanel, EquityCurve } from '../analytics/index.js';
import { SettingsPanel } from '../settings/index.js';

export class DashboardController {
  constructor() {
    /** @type {Map<string, BaseComponent>} */
    this._components = new Map();
    
    this._initialized = false;
  }

  // ─────────────────────────────────────────────────────────
  // Inicialización
  // ─────────────────────────────────────────────────────────

  async init() {
    if (this._initialized) return;
    
    console.log('[Dashboard] Initializing...');
    
    try {
      // 1. Inicializar servicios
      await this._initServices();
      
      // 2. Montar componentes
      this._mountComponents();
      
      // 3. Cargar datos iniciales
      await this._loadInitialData();
      
      // 4. Conectar WebSocket
      this._connectWebSocket();
      
      // 5. Bind eventos globales
      this._bindGlobalEvents();
      
      this._initialized = true;
      console.log('[Dashboard] Ready');
      
    } catch (error) {
      console.error('[Dashboard] Init error:', error);
      this._showError('Error al inicializar el dashboard');
    }
  }

  async _initServices() {
    // Los servicios son singletons, ya están inicializados
    // Solo verificamos que existan
    if (!ApiService || !WebSocketService) {
      throw new Error('Services not available');
    }
  }

  _mountComponents() {
    // Chart principal
    this._mount('chart', ChartComponent, 'main-chart');
    
    // Selectores
    this._mount('symbolSelector', SymbolSelector, 'symbol-selector');
    this._mount('timeframeSelector', TimeframeSelector, 'timeframe-selector');
    
    // Panel de señal
    this._mount('signalPanel', SignalPanel, 'signal-panel');
    
    // Stats
    this._mount('statsPanel', StatsPanel, 'stats-panel');
    this._mount('equityCurve', EquityCurve, 'equity-curve');
    
    // Trade table
    this._mount('tradeTable', TradeTable, 'trade-table');
    
    // Settings (si existe el elemento)
    this._mount('settingsPanel', SettingsPanel, 'settings-panel');
  }

  _mount(name, ComponentClass, elementId) {
    const el = document.getElementById(elementId);
    if (!el) {
      console.warn(`[Dashboard] Element '${elementId}' not found, skipping ${name}`);
      return;
    }
    
    try {
      const component = new ComponentClass(elementId);
      component.mount();
      this._components.set(name, component);
    } catch (error) {
      console.error(`[Dashboard] Error mounting ${name}:`, error);
    }
  }

  async _loadInitialData() {
    const symbol = Store.getState().market?.currentSymbol || CONFIG.DEFAULT_SYMBOLS[0];
    
    // Cargar velas iniciales
    try {
      await ApiService.getCandles(symbol, CONFIG.DEFAULT_TIMEFRAME, 200);
    } catch (error) {
      console.warn('[Dashboard] Could not load initial candles:', error);
    }
    
    // Cargar stats
    try {
      await ApiService.getStats();
    } catch (error) {
      console.warn('[Dashboard] Could not load initial stats:', error);
    }
  }

  _connectWebSocket() {
    const symbol = Store.getState().market?.currentSymbol || CONFIG.DEFAULT_SYMBOLS[0];
    WebSocketService.connect(symbol);
  }

  // ─────────────────────────────────────────────────────────
  // Eventos globales
  // ─────────────────────────────────────────────────────────

  _bindGlobalEvents() {
    // Cambio de símbolo → reconectar WS
    Store.subscribe('market', (state, prev) => {
      if (state.currentSymbol !== prev?.currentSymbol) {
        WebSocketService.connect(state.currentSymbol);
      }
    });

    // Nueva señal → sonido
    Store.subscribe('trading', (state, prev) => {
      const newSignals = state.signals?.length || 0;
      const prevSignals = prev?.signals?.length || 0;
      
      if (newSignals > prevSignals) {
        const lastSignal = state.signals[state.signals.length - 1];
        AudioService.beepSignal(lastSignal?.signal_type);
      }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => this._handleKeyboard(e));

    // Nav items → modal de settings
    this._bindNavItems();
  }

  _bindNavItems() {
    const settingsNav = document.querySelector('[data-view="settings"]');
    if (settingsNav) {
      settingsNav.addEventListener('click', (e) => {
        e.preventDefault();
        this._openSettingsModal();
      });
    }
  }

  _openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  _closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  _handleKeyboard(e) {
    // Solo si no hay foco en input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    const symbols = CONFIG.DEFAULT_SYMBOLS;
    
    // 1-9: Cambiar símbolo
    if (e.key >= '1' && e.key <= '9') {
      const idx = parseInt(e.key) - 1;
      if (idx < symbols.length) {
        Store.setState('market', { currentSymbol: symbols[idx] });
      }
      return;
    }

    // M: Mute/unmute audio
    if (e.key === 'm' || e.key === 'M') {
      const muted = Store.getState().ui?.audioMuted;
      Store.setState('ui', { audioMuted: !muted });
      return;
    }

    // S: Toggle settings modal
    if (e.key === 's' || e.key === 'S') {
      const modal = document.getElementById('settings-modal');
      if (modal) {
        modal.style.display = modal.style.display === 'flex' ? 'none' : 'flex';
      }
      return;
    }

    // Escape: Cerrar modal
    if (e.key === 'Escape') {
      this._closeSettingsModal();
      return;
    }
  }

  // ─────────────────────────────────────────────────────────
  // API pública
  // ─────────────────────────────────────────────────────────

  getComponent(name) {
    return this._components.get(name);
  }

  destroy() {
    // Desmontar todos los componentes
    this._components.forEach((component, name) => {
      try {
        component.unmount();
      } catch (error) {
        console.error(`[Dashboard] Error unmounting ${name}:`, error);
      }
    });
    this._components.clear();
    
    // Desconectar WS
    WebSocketService.disconnect();
    
    this._initialized = false;
  }

  // ─────────────────────────────────────────────────────────
  // Utilidades
  // ─────────────────────────────────────────────────────────

  _showError(message) {
    const el = document.getElementById('error-container');
    if (el) {
      el.textContent = message;
      el.style.display = 'block';
    } else {
      console.error('[Dashboard]', message);
    }
  }
}

// Singleton
export const Dashboard = new DashboardController();
export default Dashboard;
