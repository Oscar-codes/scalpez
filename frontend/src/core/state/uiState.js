/**
 * QuantPulse – UI State Slice
 * =============================
 * Estado relacionado con la interfaz de usuario.
 *
 * RESPONSABILIDADES:
 *   - Estado de paneles (collapsed, expanded)
 *   - Vista/ruta activa
 *   - Filtros aplicados
 *   - Notificaciones
 *   - Preferencias de usuario
 */

import Store from './store.js';

// ── Estado Inicial ──
const initialState = {
  // Navegación
  currentView: 'dashboard',     // 'dashboard' | 'analytics' | 'settings'
  currentTimeframe: 5,          // Timeframe en segundos (5, 15, 30, 60, 300)
  sidebarCollapsed: false,
  audioMuted: false,
  
  // Paneles
  panels: {
    signals: { expanded: true },
    stats: { expanded: true },
    equity: { expanded: true },
    trades: { expanded: true },
  },
  
  // Filtros
  filters: {
    tradeStatus: 'all',         // 'all' | 'profit' | 'loss' | 'expired'
    signalType: 'all',          // 'all' | 'buy' | 'sell'
    dateRange: null,            // { from, to } | null
  },
  
  // Notificaciones
  notifications: [],            // [{ id, type, message, timestamp }]
  
  // Preferencias
  preferences: {
    soundEnabled: true,
    theme: 'dark',
    chartStyle: 'candlestick',
  },
  
  // Loading states
  loading: {
    candles: false,
    stats: false,
    trades: false,
  },
  
  // Errores
  lastError: null,
};

// ── Registrar Slice ──
Store.registerSlice('ui', initialState);

// ── Actions ──

const UIState = {
  /**
   * Cambiar vista actual.
   * @param {string} view
   */
  setView(view) {
    Store.setState('ui.currentView', view);
  },

  /**
   * Toggle sidebar.
   */
  toggleSidebar() {
    const current = Store.getState('ui.sidebarCollapsed');
    Store.setState('ui.sidebarCollapsed', !current);
  },

  /**
   * Cambiar timeframe.
   * @param {number} timeframe - Segundos
   */
  setTimeframe(timeframe) {
    Store.setState('ui.currentTimeframe', timeframe);
  },

  /**
   * Toggle audio mute.
   */
  toggleAudioMute() {
    const current = Store.getState('ui.audioMuted');
    Store.setState('ui.audioMuted', !current);
  },

  /**
   * Expandir/colapsar panel.
   * @param {string} panelName
   */
  togglePanel(panelName) {
    const panels = Store.getState('ui.panels');
    if (!panels[panelName]) return;
    
    Store.setState('ui.panels', {
      ...panels,
      [panelName]: {
        ...panels[panelName],
        expanded: !panels[panelName].expanded,
      },
    });
  },

  /**
   * Establecer filtro.
   * @param {string} filterName
   * @param {*} value
   */
  setFilter(filterName, value) {
    const filters = Store.getState('ui.filters');
    Store.setState('ui.filters', {
      ...filters,
      [filterName]: value,
    });
  },

  /**
   * Limpiar todos los filtros.
   */
  clearFilters() {
    Store.setState('ui.filters', {
      tradeStatus: 'all',
      signalType: 'all',
      dateRange: null,
    });
  },

  /**
   * Añadir notificación.
   * @param {'info'|'success'|'warning'|'error'} type
   * @param {string} message
   * @param {number} [duration=5000] - Auto-dismiss en ms (0 = no auto)
   */
  addNotification(type, message, duration = 5000) {
    const notifications = Store.getState('ui.notifications') || [];
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2);
    
    const notification = {
      id,
      type,
      message,
      timestamp: Date.now(),
    };
    
    Store.setState('ui.notifications', [...notifications, notification]);
    
    if (duration > 0) {
      setTimeout(() => this.removeNotification(id), duration);
    }
    
    return id;
  },

  /**
   * Remover notificación.
   * @param {string} id
   */
  removeNotification(id) {
    const notifications = Store.getState('ui.notifications') || [];
    Store.setState('ui.notifications', notifications.filter(n => n.id !== id));
  },

  /**
   * Limpiar todas las notificaciones.
   */
  clearNotifications() {
    Store.setState('ui.notifications', []);
  },

  /**
   * Actualizar preferencia.
   * @param {string} key
   * @param {*} value
   */
  setPreference(key, value) {
    const prefs = Store.getState('ui.preferences');
    Store.setState('ui.preferences', {
      ...prefs,
      [key]: value,
    });
    
    // Persistir en localStorage
    try {
      localStorage.setItem('qp_preferences', JSON.stringify({
        ...prefs,
        [key]: value,
      }));
    } catch (e) { /* silent */ }
  },

  /**
   * Cargar preferencias desde localStorage.
   */
  loadPreferences() {
    try {
      const saved = localStorage.getItem('qp_preferences');
      if (saved) {
        const prefs = JSON.parse(saved);
        Store.setState('ui.preferences', {
          ...Store.getState('ui.preferences'),
          ...prefs,
        });
      }
    } catch (e) { /* silent */ }
  },

  /**
   * Establecer estado de loading.
   * @param {string} key
   * @param {boolean} isLoading
   */
  setLoading(key, isLoading) {
    const loading = Store.getState('ui.loading');
    Store.setState('ui.loading', {
      ...loading,
      [key]: isLoading,
    });
  },

  /**
   * Establecer error.
   * @param {string|null} error
   */
  setError(error) {
    Store.setState('ui.lastError', error);
    if (error) {
      this.addNotification('error', error);
    }
  },
};

export { UIState, initialState as uiInitialState };
export default UIState;
