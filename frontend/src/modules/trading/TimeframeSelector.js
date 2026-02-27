/**
 * QuantPulse – Timeframe Selector Component
 * ============================================
 * Selector de timeframe con indicador visual.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { UIState } from '../../core/state/uiState.js';
import { CONFIG } from '../../core/config.js';

export class TimeframeSelector extends BaseComponent {
  constructor(containerId) {
    super(containerId);
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    this._renderTimeframes();
    
    // Suscribirse a cambios de UI
    this.subscribeToStore('ui', (state) => this._onUIChange(state));
  }

  _renderTimeframes() {
    const timeframes = CONFIG.TIMEFRAMES;
    const current = Store.getState().ui?.currentTimeframe || CONFIG.DEFAULT_TIMEFRAME;

    this.element.innerHTML = '';
    this.element.className = 'timeframe-selector';

    timeframes.forEach(tf => {
      const btn = document.createElement('button');
      btn.className = `tf-btn ${tf.value === current ? 'active' : ''}`;
      btn.dataset.timeframe = tf.value;
      btn.textContent = tf.label;
      btn.title = tf.label;
      btn.addEventListener('click', () => this._selectTimeframe(tf.value));
      this.element.appendChild(btn);
    });
  }

  // ─────────────────────────────────────────────────────────
  // Interacción
  // ─────────────────────────────────────────────────────────

  _selectTimeframe(timeframe) {
    const current = Store.getState().ui?.currentTimeframe;
    if (timeframe === current) return;

    // Actualizar estado global
    UIState.setTimeframe(timeframe);

    // Actualizar clases activas
    this.element.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.timeframe === timeframe);
    });
  }

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onUIChange(ui) {
    const current = ui.currentTimeframe;
    
    // Asegurar sincronización
    this.element.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.timeframe === current);
    });
  }

  render() {
    // No usado
  }
}

export default TimeframeSelector;
