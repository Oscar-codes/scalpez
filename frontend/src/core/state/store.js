/**
 * QuantPulse – Central Store (Redux-like Pattern)
 * =================================================
 * Store reactivo centralizado para estado global.
 *
 * PRINCIPIOS:
 *   1. Single Source of Truth
 *   2. Estado inmutable (devuelve copias)
 *   3. Cambios solo vía dispatch/setState
 *   4. Suscripción reactiva via subscribe()
 *
 * ARQUITECTURA:
 *   ┌─────────────────────────────────────────┐
 *   │                 STORE                   │
 *   │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
 *   │  │ market  │ │ trading │ │   ui    │   │
 *   │  │  State  │ │  State  │ │  State  │   │
 *   │  └─────────┘ └─────────┘ └─────────┘   │
 *   └─────────────────────────────────────────┘
 *         ▲                           │
 *         │ dispatch(action)          │ notify
 *         │                           ▼
 *   ┌─────────────┐           ┌─────────────┐
 *   │  Services   │           │ Components  │
 *   │  (WS, API)  │           │ (subscribed)│
 *   └─────────────┘           └─────────────┘
 *
 * USO:
 *   // Leer estado
 *   const symbol = Store.getState('market.currentSymbol');
 *   
 *   // Actualizar estado
 *   Store.setState('market.currentSymbol', 'R_100');
 *   
 *   // Suscribirse a cambios
 *   const unsubscribe = Store.subscribe('market', (state) => {
 *     console.log('Market state changed:', state);
 *   });
 */

import EventBus from './eventBus.js';
import CONFIG from './config.js';

class StoreClass {
  constructor() {
    /** @type {Object} Estado global particionado por slices */
    this._state = {};
    
    /** @type {Map<string, Set<Function>>} Suscriptores por slice */
    this._subscribers = new Map();
    
    /** @type {Array<Function>} Middlewares */
    this._middlewares = [];
    
    /** @type {boolean} Modo debug */
    this._debug = false;
  }

  /**
   * Registrar un slice de estado con su valor inicial.
   * @param {string} sliceName
   * @param {Object} initialState
   */
  registerSlice(sliceName, initialState) {
    if (this._state[sliceName]) {
      console.warn(`[Store] Slice '${sliceName}' ya existe, sobrescribiendo.`);
    }
    this._state[sliceName] = { ...initialState };
    this._subscribers.set(sliceName, new Set());
  }

  /**
   * Obtener estado completo o parcial.
   * @param {string} [path] - Ej: 'market.currentSymbol' o 'market'
   * @returns {*}
   */
  getState(path) {
    if (!path) {
      // Retorna copia profunda del estado completo
      return JSON.parse(JSON.stringify(this._state));
    }

    const parts = path.split('.');
    let value = this._state;
    
    for (const part of parts) {
      if (value === undefined || value === null) return undefined;
      value = value[part];
    }
    
    // Retorna copia si es objeto
    if (typeof value === 'object' && value !== null) {
      return Array.isArray(value) ? [...value] : { ...value };
    }
    return value;
  }

  /**
   * Actualizar estado.
   * @param {string} path - Ej: 'market.currentSymbol'
   * @param {*} value
   * @param {Object} [meta] - Metadata opcional para middlewares
   */
  setState(path, value, meta = {}) {
    const parts = path.split('.');
    const sliceName = parts[0];
    
    if (!this._state[sliceName]) {
      console.error(`[Store] Slice '${sliceName}' no registrado.`);
      return;
    }

    // Obtener valor anterior
    const oldValue = this.getState(path);
    
    // Shallow compare - solo actualizar si cambió
    if (oldValue === value) return;
    
    // Ejecutar middlewares
    const action = { path, value, oldValue, meta };
    for (const middleware of this._middlewares) {
      const result = middleware(action, this._state);
      if (result === false) return; // Middleware puede cancelar
    }

    // Aplicar cambio
    if (parts.length === 1) {
      // Actualizar slice completo
      this._state[sliceName] = value;
    } else {
      // Actualizar propiedad dentro del slice
      let target = this._state;
      for (let i = 0; i < parts.length - 1; i++) {
        target = target[parts[i]];
      }
      target[parts[parts.length - 1]] = value;
    }

    if (this._debug) {
      console.log(`[Store] ${path}:`, oldValue, '→', value);
    }

    // Notificar suscriptores del slice
    this._notifySubscribers(sliceName);
    
    // Emitir evento en EventBus para compatibilidad
    EventBus.emit(`store:${path}`, value);
  }

  /**
   * Suscribirse a cambios de un slice.
   * @param {string} sliceName
   * @param {Function} callback - Recibe el estado del slice
   * @returns {Function} Función para desuscribirse
   */
  subscribe(sliceName, callback) {
    if (!this._subscribers.has(sliceName)) {
      this._subscribers.set(sliceName, new Set());
    }
    
    this._subscribers.get(sliceName).add(callback);
    
    // Llamar inmediatamente con estado actual
    callback(this._state[sliceName]);
    
    // Retornar unsubscribe function
    return () => {
      const subs = this._subscribers.get(sliceName);
      if (subs) subs.delete(callback);
    };
  }

  /**
   * Notificar a todos los suscriptores de un slice.
   * @param {string} sliceName
   * @private
   */
  _notifySubscribers(sliceName) {
    const subscribers = this._subscribers.get(sliceName);
    if (!subscribers) return;
    
    const state = this._state[sliceName];
    for (const callback of subscribers) {
      try {
        callback(state);
      } catch (err) {
        console.error(`[Store] Error en subscriber de '${sliceName}':`, err);
      }
    }
  }

  /**
   * Registrar middleware.
   * Middleware: (action, state) => boolean|void
   * Retornar false para cancelar la acción.
   * @param {Function} middleware
   */
  use(middleware) {
    this._middlewares.push(middleware);
  }

  /**
   * Batch updates - múltiples cambios notifican una sola vez.
   * @param {Function} fn - Función que ejecuta múltiples setState
   */
  batch(fn) {
    const affectedSlices = new Set();
    const originalNotify = this._notifySubscribers.bind(this);
    
    // Interceptar notificaciones
    this._notifySubscribers = (sliceName) => {
      affectedSlices.add(sliceName);
    };
    
    try {
      fn();
    } finally {
      // Restaurar y notificar una vez por slice
      this._notifySubscribers = originalNotify;
      for (const slice of affectedSlices) {
        this._notifySubscribers(slice);
      }
    }
  }

  /**
   * Reset de un slice a su estado inicial.
   * @param {string} sliceName
   * @param {Object} initialState
   */
  resetSlice(sliceName, initialState) {
    this._state[sliceName] = { ...initialState };
    this._notifySubscribers(sliceName);
  }

  /**
   * Activar modo debug.
   * @param {boolean} enabled
   */
  setDebug(enabled) {
    this._debug = enabled;
  }

  /**
   * Obtener snapshot del estado para debugging.
   * @returns {string}
   */
  snapshot() {
    return JSON.stringify(this._state, null, 2);
  }
}

// Singleton
const Store = new StoreClass();

export { Store, StoreClass };
export default Store;
