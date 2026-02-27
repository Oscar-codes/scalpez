/**
 * QuantPulse – Audio Service
 * ============================
 * Alertas de audio usando Web Audio API.
 * Sin archivos externos, genera tonos por código.
 */

import EventBus from '../core/eventBus.js';
import Store from '../core/state/store.js';

class AudioServiceClass {
  constructor() {
    /** @type {AudioContext|null} */
    this._ctx = null;
  }

  /**
   * Obtener o crear AudioContext.
   * @returns {AudioContext}
   * @private
   */
  _getContext() {
    if (!this._ctx) {
      this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return this._ctx;
  }

  /**
   * Verificar si el audio está habilitado en preferencias.
   * @returns {boolean}
   */
  isEnabled() {
    return Store.getState('ui.preferences.soundEnabled') ?? true;
  }

  /**
   * Emitir un tono.
   * @param {number} freq - Frecuencia en Hz
   * @param {number} duration - Duración en segundos
   * @param {'sine'|'square'|'triangle'|'sawtooth'} type
   * @param {number} volume - 0.0 a 1.0
   */
  beep(freq = 880, duration = 0.15, type = 'sine', volume = 0.25) {
    if (!this.isEnabled()) return;
    
    try {
      const ctx = this._getContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(volume, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration);
    } catch (e) {
      // Audio puede fallar sin interacción previa
    }
  }

  /**
   * Alerta para nueva señal (doble beep agudo).
   */
  alertSignal() {
    this.beep(1200, 0.12, 'sine');
    setTimeout(() => this.beep(1500, 0.12, 'sine'), 150);
  }

  /**
   * Alerta para trade abierto.
   */
  alertTradeOpened() {
    this.beep(880, 0.18, 'triangle');
  }

  /**
   * Alerta para trade con profit (beep ascendente).
   */
  alertTradeProfit() {
    this.beep(800, 0.1, 'sine');
    setTimeout(() => this.beep(1100, 0.1, 'sine'), 120);
    setTimeout(() => this.beep(1400, 0.15, 'sine'), 240);
  }

  /**
   * Alerta para trade con loss (beep descendente).
   */
  alertTradeLoss() {
    this.beep(600, 0.15, 'square');
    setTimeout(() => this.beep(400, 0.2, 'square'), 180);
  }

  /**
   * Registrar listeners para eventos de trading.
   */
  bindToTradeEvents() {
    EventBus.on('trade:signal', () => this.alertSignal());
    EventBus.on('trade:opened', () => this.alertTradeOpened());
    EventBus.on('trade:closed', (trade) => {
      if (trade.result === 'PROFIT' || trade.status === 'PROFIT') {
        this.alertTradeProfit();
      } else {
        this.alertTradeLoss();
      }
    });
  }
}

// Singleton
const AudioService = new AudioServiceClass();

export { AudioService, AudioServiceClass };
export default AudioService;
