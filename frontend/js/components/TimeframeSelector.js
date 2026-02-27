/**
 * QuantPulse – Timeframe Selector Component
 * ============================================
 * Selector de timeframe activo con botones: 5m, 15m, 30m, 1h.
 *
 * RESPONSABILIDADES:
 *   1. Renderizar botones de timeframes disponibles
 *   2. Resaltar timeframe activo
 *   3. Al cambiar → emitir 'state:activeTimeframe'
 *   4. Sincronizar con el servidor vía callback
 *
 * CÓMO SE INTEGRA:
 *   - Lee availableTimeframes y activeTimeframe de StateManager
 *   - Al click: llama onChangeCb(tf) (provisto por app.js)
 *   - Se suscribe a 'state:activeTimeframe' para actualizar UI
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const TimeframeSelector = (() => {
  /** @type {HTMLElement|null} */
  let _container = null;

  /** @type {Function|null} callback cuando el usuario cambia TF */
  let _onChangeCb = null;

  // ── Inicialización ────────────────────────────────────────────

  /**
   * Montar el componente en el DOM.
   * @param {string} containerId  ID del elemento contenedor
   * @param {Function} [onChangeCb]  Callback async (tf) => {...}
   */
  function init(containerId, onChangeCb = null) {
    _container = document.getElementById(containerId);
    if (!_container) return console.error('[TFSelector] Container no encontrado');

    _onChangeCb = onChangeCb;
    _render();
    _bindEvents();
  }

  // ── Render ────────────────────────────────────────────────────

  function _render() {
    const timeframes = StateManager.get('availableTimeframes');
    const active = StateManager.get('activeTimeframe');

    _container.innerHTML = '';

    // Label
    const label = document.createElement('span');
    label.className = 'tf-label';
    label.textContent = 'TF';
    _container.appendChild(label);

    // Timeframe buttons
    timeframes.forEach(tf => {
      const btn = document.createElement('button');
      btn.className = `tf-btn ${tf === active ? 'active' : ''}`;
      btn.dataset.tf = tf;
      btn.textContent = tf;
      btn.addEventListener('click', () => _selectTimeframe(tf));
      _container.appendChild(btn);
    });
  }

  // ── Interacción ───────────────────────────────────────────────

  async function _selectTimeframe(tf) {
    if (tf === StateManager.get('activeTimeframe')) return;

    // Actualizar UI inmediatamente
    _updateActiveBtn(tf);

    // Callback al orquestador (app.js maneja server + refetch)
    if (_onChangeCb) {
      await _onChangeCb(tf);
    }
  }

  function _updateActiveBtn(tf) {
    if (!_container) return;
    _container.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tf === tf);
    });
  }

  // ── Suscripciones ─────────────────────────────────────────────

  function _bindEvents() {
    // Sincronizar si el TF cambia externamente
    EventBus.on('state:activeTimeframe', (tf) => {
      _updateActiveBtn(tf);
    });
  }

  return Object.freeze({ init });
})();

export default TimeframeSelector;
