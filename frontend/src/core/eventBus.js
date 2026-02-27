/**
 * QuantPulse – EventBus (Publisher / Subscriber)
 * ================================================
 * Bus de eventos desacoplado para comunicación entre módulos.
 *
 * ARQUITECTURA:
 *   WebSocketService  ──publish('ws:tick', data)──▸  EventBus
 *   EventBus  ──notify──▸  ChartComponent (suscrito)
 *   Store     ──notify via EventBus──▸  UI Components
 *
 * CONVENCIÓN DE NOMBRES:
 *   'ws:{event}'        → evento del WebSocket
 *   'store:{slice}'     → cambio en slice del store
 *   'ui:{action}'       → acción de UI
 *   'route:{name}'      → cambio de ruta
 *
 * MEJORAS SOBRE VERSIÓN ANTERIOR:
 *   - Soporte para namespaces (emit wildcard)
 *   - Debug mode opcional
 *   - Prioridad de handlers
 */

class EventBusClass {
  constructor() {
    /** @type {Map<string, Set<{fn: Function, priority: number}>>} */
    this._listeners = new Map();
    this._debugMode = false;
  }

  /**
   * Activar/desactivar modo debug.
   * @param {boolean} enabled
   */
  setDebug(enabled) {
    this._debugMode = enabled;
  }

  /**
   * Suscribir callback a un evento.
   * @param {string} event     Nombre del evento
   * @param {Function} fn      Callback
   * @param {number} priority  Mayor = ejecuta primero (default: 0)
   * @returns {Function}       Cleanup function
   */
  on(event, fn, priority = 0) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    
    const handler = { fn, priority };
    this._listeners.get(event).add(handler);

    // Retorna cleanup function
    return () => this.off(event, fn);
  }

  /**
   * Suscripción que se auto-remueve tras primera ejecución.
   * @param {string} event
   * @param {Function} fn
   */
  once(event, fn) {
    const wrapper = (data) => {
      this.off(event, wrapper);
      fn(data);
    };
    return this.on(event, wrapper);
  }

  /**
   * Desuscribir callback específico.
   * @param {string} event
   * @param {Function} fn
   */
  off(event, fn) {
    const set = this._listeners.get(event);
    if (!set) return;
    
    for (const handler of set) {
      if (handler.fn === fn) {
        set.delete(handler);
        break;
      }
    }
    
    if (set.size === 0) {
      this._listeners.delete(event);
    }
  }

  /**
   * Emitir evento a todos los suscriptores.
   * Handlers se ejecutan ordenados por prioridad (mayor primero).
   * @param {string} event
   * @param {*} data
   */
  emit(event, data) {
    if (this._debugMode) {
      console.log(`[EventBus] ${event}`, data);
    }

    const set = this._listeners.get(event);
    if (!set) return;

    // Ordenar por prioridad (mayor primero)
    const handlers = [...set].sort((a, b) => b.priority - a.priority);
    
    for (const { fn } of handlers) {
      try {
        fn(data);
      } catch (err) {
        console.error(`[EventBus] Error en handler de '${event}':`, err);
      }
    }
  }

  /**
   * Emitir evento que coincida con un namespace.
   * Ej: emitNamespace('ws', data) emite a todos los 'ws:*'
   * @param {string} namespace
   * @param {*} data
   */
  emitNamespace(namespace, data) {
    const prefix = `${namespace}:`;
    for (const [event] of this._listeners) {
      if (event.startsWith(prefix)) {
        this.emit(event, data);
      }
    }
  }

  /**
   * Limpiar todos los listeners de un namespace.
   * @param {string} namespace
   */
  clearNamespace(namespace) {
    const prefix = `${namespace}:`;
    for (const [event] of this._listeners) {
      if (event.startsWith(prefix)) {
        this._listeners.delete(event);
      }
    }
  }

  /**
   * Limpiar todos los listeners.
   */
  clear() {
    this._listeners.clear();
  }

  /**
   * Obtener lista de eventos con listeners activos.
   * @returns {string[]}
   */
  getActiveEvents() {
    return [...this._listeners.keys()];
  }
}

// Singleton
const EventBus = new EventBusClass();

export { EventBus, EventBusClass };
export default EventBus;
