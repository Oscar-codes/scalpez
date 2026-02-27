/**
 * QuantPulse – WebSocket Service
 * ================================
 * Conexión WebSocket al backend con reconexión automática.
 *
 * RESPONSABILIDADES:
 *   1. Conectar a ws://{host}/ws/market
 *   2. Parsear mensajes JSON del backend
 *   3. Publicar en EventBus (desacoplado de UI)
 *   4. Reconectar con backoff exponencial
 *   5. Notificar estado de conexión al StateManager
 *
 * RECONEXIÓN CON BACKOFF EXPONENCIAL:
 *   Intento 1: 1s  →  2: 2s  →  3: 4s  →  4: 8s  →  max: 30s
 *   Se resetea a 1s tras conexión exitosa.
 *
 * CÓMO SE EVITAN MEMORY LEAKS:
 *   - Al reconectar, se cierra el socket anterior si existe.
 *   - No se crean múltiples conexiones simultáneas.
 *   - Los listeners onopen/onclose/onmessage se asignan una sola vez.
 *   - _reconnectTimer se limpia antes de programar otro.
 *
 * MAPPING DE EVENTOS BACKEND → EVENTBUS FRONTEND:
 *   { type: "tick", data: {...} }          → 'ws:tick'
 *   { type: "candle", data: {...} }        → 'ws:candle'
 *   { type: "indicators", data: {...} }    → 'ws:indicators'
 *   { type: "signal", data: {...} }        → 'ws:signal'
 *   { type: "trade_opened", data: {...} }  → 'ws:trade_opened'
 *   { type: "trade_closed", data: {...} }  → 'ws:trade_closed'
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const WebSocketService = (() => {
  /** @type {WebSocket|null} */
  let _ws = null;

  /** @type {number|null} */
  let _reconnectTimer = null;

  /** Backoff exponencial: empieza en 1s, max 30s */
  let _reconnectDelay = 1000;
  const _maxDelay = 30000;

  /** Evitar múltiples conexiones simultáneas */
  let _connecting = false;

  /** URL base del WebSocket */
  const _getUrl = () => {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.host || 'localhost:8888';
    return `${protocol}//${host}/ws/market`;
  };

  // ── Conexión ──────────────────────────────────────────────────

  /**
   * Iniciar conexión WebSocket.
   * Si ya hay una activa, la cierra primero.
   */
  function connect() {
    if (_connecting) return;
    _connecting = true;

    // Limpiar socket previo si existe
    if (_ws) {
      try { _ws.close(); } catch (e) { /* ignorar */ }
      _ws = null;
    }

    StateManager.set('connectionStatus', 'connecting');
    const url = _getUrl();
    console.log(`[WS] Conectando a ${url}...`);

    try {
      _ws = new WebSocket(url);
    } catch (err) {
      console.error('[WS] Error creando WebSocket:', err);
      _connecting = false;
      _scheduleReconnect();
      return;
    }

    _ws.onopen = _handleOpen;
    _ws.onclose = _handleClose;
    _ws.onerror = _handleError;
    _ws.onmessage = _handleMessage;
  }

  /**
   * Cerrar conexión manualmente (no reconecta).
   */
  function disconnect() {
    _clearReconnect();
    if (_ws) {
      try { _ws.close(1000, 'Client disconnect'); } catch (e) { /* ok */ }
      _ws = null;
    }
    StateManager.set('connectionStatus', 'disconnected');
  }

  // ── Handlers ──────────────────────────────────────────────────

  /** @type {number|null} Intervalo de ping keepalive */
  let _pingInterval = null;

  function _handleOpen() {
    console.log('[WS] Conectado ✓');
    _connecting = false;
    _reconnectDelay = 1000; // resetear backoff
    _clearReconnect();
    StateManager.set('connectionStatus', 'connected');

    // Iniciar ping keepalive cada 25s para evitar timeout
    _clearPing();
    _pingInterval = setInterval(() => {
      if (_ws && _ws.readyState === WebSocket.OPEN) {
        try { _ws.send(JSON.stringify({ type: 'ping' })); } catch (e) { /* ok */ }
      }
    }, 25000);
  }

  function _handleClose(event) {
    console.warn(`[WS] Desconectado (code=${event.code}, reason=${event.reason})`);
    _connecting = false;
    _ws = null;
    _clearPing();
    StateManager.set('connectionStatus', 'disconnected');
    _scheduleReconnect();
  }

  function _handleError(event) {
    console.error('[WS] Error:', event);
    // onclose se dispara después de onerror, ahí reconecta
  }

  /**
   * Procesar mensaje JSON del backend.
   * Mapea type → evento 'ws:{type}' en EventBus.
   *
   * FORMATO ESPERADO:
   *   { "type": "tick|candle|signal|...", "data": {...} }
   */
  function _handleMessage(event) {
    try {
      const msg = JSON.parse(event.data);
      if (!msg.type || msg.data === undefined) return;

      // Ignorar ping/pong del keepalive
      if (msg.type === 'ping' || msg.type === 'pong') return;

      // Publicar en EventBus para que los componentes consuman
      EventBus.emit(`ws:${msg.type}`, msg.data);
    } catch (err) {
      console.error('[WS] Error parseando mensaje:', err);
    }
  }

  // ── Reconexión ────────────────────────────────────────────────

  function _scheduleReconnect() {
    _clearReconnect();
    console.log(`[WS] Reconectando en ${_reconnectDelay / 1000}s...`);

    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null;
      connect();
    }, _reconnectDelay);

    // Backoff exponencial con cap
    _reconnectDelay = Math.min(_reconnectDelay * 2, _maxDelay);
  }

  function _clearReconnect() {
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = null;
    }
  }

  function _clearPing() {
    if (_pingInterval) {
      clearInterval(_pingInterval);
      _pingInterval = null;
    }
  }

  // ── Estado ────────────────────────────────────────────────────

  /**
   * ¿Está conectado?
   * @returns {boolean}
   */
  function isConnected() {
    return _ws !== null && _ws.readyState === WebSocket.OPEN;
  }

  return Object.freeze({ connect, disconnect, isConnected });
})();

export default WebSocketService;
