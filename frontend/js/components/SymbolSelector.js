/**
 * QuantPulse – Symbol Selector Component
 * =========================================
 * Selector de símbolo activo con indicador de precio en tiempo real.
 *
 * RESPONSABILIDADES:
 *   1. Renderizar botones de símbolos disponibles
 *   2. Mostrar precio actual y delta en tiempo real
 *   3. Mostrar estado de conexión WS (dot indicator)
 *   4. Emitir 'state:currentSymbol' al cambiar
 *
 * CÓMO SE INTEGRA:
 *   - Se suscribe a 'state:tick' para precios live
 *   - Se suscribe a 'state:connectionStatus' para indicador
 *   - Al cambiar símbolo → StateManager.set('currentSymbol')
 *     → todos los demás componentes reaccionan automáticamente
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const SymbolSelector = (() => {
  /** @type {HTMLElement|null} */
  let _container = null;

  /** Último precio previo por símbolo (para calcular delta) */
  const _prevPrices = {};

  // ── Inicialización ────────────────────────────────────────────

  /**
   * Montar el componente en el DOM.
   * @param {string} containerId  ID del elemento contenedor
   */
  function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return console.error('[SymbolSelector] Container no encontrado');

    _render();
    _bindEvents();
  }

  // ── Render ────────────────────────────────────────────────────

  function _render() {
    const symbols = StateManager.get('symbols');
    const current = StateManager.get('currentSymbol');

    _container.innerHTML = '';

    // Connection indicator
    const connDot = document.createElement('span');
    connDot.id = 'conn-indicator';
    connDot.className = 'conn-dot disconnected';
    connDot.title = 'Desconectado';
    _container.appendChild(connDot);

    // Symbol buttons
    symbols.forEach(sym => {
      const btn = document.createElement('button');
      btn.className = `symbol-btn ${sym === current ? 'active' : ''}`;
      btn.dataset.symbol = sym;
      btn.innerHTML = `
        <span class="symbol-name">${sym}</span>
        <span class="symbol-price" id="price-${sym}">--</span>
        <span class="symbol-delta" id="delta-${sym}"></span>
      `;
      btn.addEventListener('click', () => _selectSymbol(sym));
      _container.appendChild(btn);
    });
  }

  // ── Interacción ───────────────────────────────────────────────

  function _selectSymbol(symbol) {
    if (symbol === StateManager.get('currentSymbol')) return;
    StateManager.set('currentSymbol', symbol);

    // Actualizar clases activas
    _container.querySelectorAll('.symbol-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.symbol === symbol);
    });
  }

  // ── Suscripciones ─────────────────────────────────────────────

  function _bindEvents() {
    // Tick en tiempo real → actualizar precio del símbolo
    EventBus.on('state:tick', (tick) => {
      const priceEl = document.getElementById(`price-${tick.symbol}`);
      const deltaEl = document.getElementById(`delta-${tick.symbol}`);
      if (!priceEl) return;

      const price = tick.quote;
      priceEl.textContent = _formatPrice(price, tick.symbol);

      // Delta (variación desde último tick)
      const prev = _prevPrices[tick.symbol];
      if (prev !== undefined && deltaEl) {
        const diff = price - prev;
        if (diff > 0) {
          deltaEl.textContent = `▲`;
          deltaEl.className = 'symbol-delta up';
        } else if (diff < 0) {
          deltaEl.textContent = `▼`;
          deltaEl.className = 'symbol-delta down';
        } else {
          deltaEl.textContent = '';
          deltaEl.className = 'symbol-delta';
        }
      }
      _prevPrices[tick.symbol] = price;
    });

    // Estado de conexión
    EventBus.on('state:connectionStatus', (status) => {
      const dot = document.getElementById('conn-indicator');
      if (!dot) return;
      dot.className = `conn-dot ${status}`;
      const labels = {
        connected: 'Conectado',
        connecting: 'Conectando...',
        disconnected: 'Desconectado',
      };
      dot.title = labels[status] || status;
    });
  }

  // ── Helpers ───────────────────────────────────────────────────

  function _formatPrice(price, symbol) {
    // R_75 tiene precios ~37000, R_100 ~800, stpRNG ~7900
    if (price > 10000) return price.toFixed(2);
    if (price > 100) return price.toFixed(2);
    return price.toFixed(5);
  }

  return Object.freeze({ init });
})();

export default SymbolSelector;
