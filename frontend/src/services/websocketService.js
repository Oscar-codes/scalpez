/**
 * QuantPulse – WebSocket Service
 * ================================
 * Conexión WebSocket con reconexión automática.
 * Actualiza el Store directamente al recibir mensajes.
 *
 * FLUJO:
 *   Backend WS → WebSocketService → Store → Components (via subscribe)
 *
 * PRINCIPIOS:
 *   - Los componentes NO se suscriben al WS directamente
 *   - El WS actualiza el Store
 *   - Los componentes se suscriben al Store
 */

import CONFIG from '../core/config.js';
import EventBus from '../core/eventBus.js';
import Store from '../core/state/store.js';
import { MarketState } from '../core/state/marketState.js';
import { TradeState } from '../core/state/tradeState.js';

class WebSocketServiceClass {
  constructor() {
    /** @type {WebSocket|null} */
    this._ws = null;
    
    /** @type {number|null} */
    this._reconnectTimer = null;
    
    /** Backoff exponencial */
    this._reconnectDelay = CONFIG.WS_RECONNECT_INITIAL;
    
    /** Evitar múltiples conexiones */
    this._connecting = false;
    
    /** Handlers de mensajes por tipo */
    this._messageHandlers = new Map();
    
    // Registrar handlers por defecto
    this._registerDefaultHandlers();
  }

  /**
   * Obtener URL del WebSocket.
   * @returns {string}
   * @private
   */
  _getUrl() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.host || 'localhost:8888';
    return `${protocol}//${host}${CONFIG.WS_PATH}`;
  }

  /**
   * Registrar handlers por defecto que actualizan el Store.
   * @private
   */
  _registerDefaultHandlers() {
    // Tick
    this.onMessage('tick', (data) => {
      MarketState.updateTick(data);
    });

    // Vela cerrada (por timeframe)
    this.onMessage('tf_candle', (data) => {
      const activeTf = Store.getState('market.currentTimeframe');
      if (data.timeframe !== activeTf) return;
      MarketState.addCandle(data);
    });

    // Indicadores (por timeframe)
    this.onMessage('tf_indicators', (data) => {
      const activeTf = Store.getState('market.currentTimeframe');
      if (data.timeframe !== activeTf) return;
      MarketState.updateIndicators(data);
    });

    // Señal nueva
    this.onMessage('signal', (data) => {
      TradeState.addSignal(data);
      // Emitir para alertas de audio
      EventBus.emit('trade:signal', data);
    });

    // Trade abierto
    this.onMessage('trade_opened', (data) => {
      TradeState.addTradeOpened(data);
      EventBus.emit('trade:opened', data);
    });

    // Trade cerrado
    this.onMessage('trade_closed', (data) => {
      TradeState.addTradeClosed(data);
      EventBus.emit('trade:closed', data);
    });
  }

  /**
   * Registrar handler personalizado para un tipo de mensaje.
   * @param {string} type - Tipo de mensaje (ej: 'tick', 'signal')
   * @param {Function} handler
   */
  onMessage(type, handler) {
    this._messageHandlers.set(type, handler);
  }

  /**
   * Iniciar conexión.
   */
  connect() {
    if (this._connecting) return;
    this._connecting = true;

    // Limpiar socket previo
    if (this._ws) {
      try { this._ws.close(); } catch (e) { /* ignorar */ }
      this._ws = null;
    }

    MarketState.setConnectionStatus('connecting');
    const url = this._getUrl();
    console.log(`[WS] Conectando a ${url}...`);

    try {
      this._ws = new WebSocket(url);
    } catch (err) {
      console.error('[WS] Error creando WebSocket:', err);
      this._connecting = false;
      this._scheduleReconnect();
      return;
    }

    this._ws.onopen = this._handleOpen.bind(this);
    this._ws.onclose = this._handleClose.bind(this);
    this._ws.onerror = this._handleError.bind(this);
    this._ws.onmessage = this._handleMessage.bind(this);
  }

  /**
   * Cerrar conexión.
   */
  disconnect() {
    this._clearReconnect();
    if (this._ws) {
      try { this._ws.close(1000, 'Client disconnect'); } catch (e) { /* ok */ }
      this._ws = null;
    }
    MarketState.setConnectionStatus('disconnected');
  }

  /**
   * Enviar mensaje al servidor.
   * @param {Object} data
   */
  send(data) {
    if (!this.isConnected()) {
      console.warn('[WS] No conectado, mensaje no enviado');
      return false;
    }
    
    try {
      this._ws.send(JSON.stringify(data));
      return true;
    } catch (err) {
      console.error('[WS] Error enviando mensaje:', err);
      return false;
    }
  }

  /**
   * ¿Está conectado?
   * @returns {boolean}
   */
  isConnected() {
    return this._ws !== null && this._ws.readyState === WebSocket.OPEN;
  }

  // ── Handlers privados ──

  _handleOpen() {
    console.log('[WS] Conectado ✓');
    this._connecting = false;
    this._reconnectDelay = CONFIG.WS_RECONNECT_INITIAL;
    this._clearReconnect();
    MarketState.setConnectionStatus('connected');
    EventBus.emit('ws:connected');
  }

  _handleClose(event) {
    console.warn(`[WS] Desconectado (code=${event.code})`);
    this._connecting = false;
    this._ws = null;
    MarketState.setConnectionStatus('disconnected');
    EventBus.emit('ws:disconnected', { code: event.code, reason: event.reason });
    this._scheduleReconnect();
  }

  _handleError(event) {
    console.error('[WS] Error:', event);
    EventBus.emit('ws:error', event);
  }

  /**
   * Procesar mensaje y actualizar Store.
   * @param {MessageEvent} event
   * @private
   */
  _handleMessage(event) {
    try {
      const msg = JSON.parse(event.data);
      if (!msg.type || msg.data === undefined) return;

      // Buscar handler registrado
      const handler = this._messageHandlers.get(msg.type);
      if (handler) {
        handler(msg.data);
      }

      // También emitir en EventBus para compatibilidad
      EventBus.emit(`ws:${msg.type}`, msg.data);
    } catch (err) {
      console.error('[WS] Error parseando mensaje:', err);
    }
  }

  _scheduleReconnect() {
    this._clearReconnect();
    console.log(`[WS] Reconectando en ${this._reconnectDelay / 1000}s...`);

    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, this._reconnectDelay);

    // Backoff exponencial con cap
    this._reconnectDelay = Math.min(
      this._reconnectDelay * 2,
      CONFIG.WS_RECONNECT_MAX
    );
  }

  _clearReconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }
}

// Singleton
const WebSocketService = new WebSocketServiceClass();

export { WebSocketService, WebSocketServiceClass };
export default WebSocketService;
