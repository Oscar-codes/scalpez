/**
 * QuantPulse – EventBus (Publisher / Subscriber interno)
 * ========================================================
 * Bus de eventos desacoplado para comunicación entre componentes.
 *
 * ARQUITECTURA:
 *   WebSocketService  ──publish('ws:tick', data)──▸  EventBus
 *   EventBus  ──notify──▸  ChartComponent (suscrito a 'ws:tick')
 *   EventBus  ──notify──▸  StatsPanel     (suscrito a 'ws:stats_update')
 *
 * POR QUÉ UN EVENTBUS INTERNO:
 *   1. Desacopla WebSocket de UI → los componentes no saben de WS.
 *   2. Permite agregar nuevos componentes sin tocar el servicio WS.
 *   3. Facilita testing: se puede emitir eventos sintéticos.
 *   4. Un componente se puede suscribir a múltiples eventos.
 *   5. Escalabilidad: agregar un nuevo panel = suscribirse a eventos.
 *
 * CONVENCIÓN DE NOMBRES:
 *   'ws:tick'           → evento que viene del WebSocket
 *   'ws:candle'         → vela cerrada desde WS
 *   'ws:signal'         → señal desde WS
 *   'ws:trade_opened'   → trade abierto desde WS
 *   'ws:trade_closed'   → trade cerrado desde WS
 *   'ws:indicators'     → indicadores desde WS
 *   'state:symbol'      → cambio de símbolo seleccionado
 *   'state:connection'  → cambio estado de conexión
 *   'ui:filter'         → filtro aplicado en UI
 *
 * CÓMO SE EVITAN MEMORY LEAKS:
 *   - off() remueve listeners por referencia exacta.
 *   - once() auto-remueve después de la primera invocación.
 *   - clear() limpia todo (útil en reconexión).
 */

const EventBus = (() => {
  /** @type {Map<string, Set<Function>>} */
  const _listeners = new Map();

  /**
   * Suscribir un callback a un evento.
   * @param {string} event  Nombre del evento
   * @param {Function} fn   Callback a ejecutar
   * @returns {Function}    Función de desuscripción (cleanup)
   */
  function on(event, fn) {
    if (!_listeners.has(event)) {
      _listeners.set(event, new Set());
    }
    _listeners.get(event).add(fn);

    // Retorna cleanup function para facilitar desuscripción
    return () => off(event, fn);
  }

  /**
   * Suscribir un callback que se ejecuta UNA sola vez.
   * Se auto-remueve tras la primera invocación.
   * @param {string} event
   * @param {Function} fn
   */
  function once(event, fn) {
    const wrapper = (data) => {
      off(event, wrapper);
      fn(data);
    };
    on(event, wrapper);
  }

  /**
   * Desuscribir un callback específico de un evento.
   * @param {string} event
   * @param {Function} fn
   */
  function off(event, fn) {
    const set = _listeners.get(event);
    if (set) {
      set.delete(fn);
      if (set.size === 0) _listeners.delete(event);
    }
  }

  /**
   * Emitir un evento a todos los suscriptores.
   * Es síncrono → los handlers se ejecutan en orden de suscripción.
   * Errores en un handler NO afectan a los demás (try/catch).
   * @param {string} event
   * @param {*} data
   */
  function emit(event, data) {
    const set = _listeners.get(event);
    if (!set) return;
    for (const fn of set) {
      try {
        fn(data);
      } catch (err) {
        console.error(`[EventBus] Error en handler de '${event}':`, err);
      }
    }
  }

  /**
   * Limpiar TODOS los listeners. Usado en reconexión o teardown.
   */
  function clear() {
    _listeners.clear();
  }

  /**
   * Debug: listar eventos activos y cantidad de listeners.
   * @returns {Object}
   */
  function debug() {
    const info = {};
    for (const [event, set] of _listeners) {
      info[event] = set.size;
    }
    return info;
  }

  return Object.freeze({ on, once, off, emit, clear, debug });
})();

export default EventBus;
