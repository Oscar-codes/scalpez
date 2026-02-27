/**
 * QuantPulse – Symbol Selector Component
 * =========================================
 * Selector de símbolo con indicador de precio en tiempo real.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { MarketState } from '../../core/state/marketState.js';
import { CONFIG } from '../../core/config.js';

export class SymbolSelector extends BaseComponent {
  constructor(containerId) {
    super(containerId);
    
    /** Último precio por símbolo (para calcular delta) */
    this._prevPrices = {};
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    this._renderSymbols();
    
    // Suscribirse a cambios de mercado
    this.subscribeToStore('market', (state) => this._onMarketChange(state));
  }

  _renderSymbols() {
    const symbols = CONFIG.DEFAULT_SYMBOLS;
    const current = Store.getState().market?.currentSymbol || symbols[0];

    this.element.innerHTML = '';

    // Connection indicator
    const connDot = document.createElement('span');
    connDot.id = 'conn-indicator';
    connDot.className = 'conn-dot disconnected';
    connDot.title = 'Desconectado';
    this.element.appendChild(connDot);

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
      btn.addEventListener('click', () => this._selectSymbol(sym));
      this.element.appendChild(btn);
    });
  }

  // ─────────────────────────────────────────────────────────
  // Interacción
  // ─────────────────────────────────────────────────────────

  _selectSymbol(symbol) {
    const current = Store.getState().market?.currentSymbol;
    if (symbol === current) return;

    // Actualizar estado global
    MarketState.setCurrentSymbol(symbol);

    // Actualizar clases activas
    this.element.querySelectorAll('.symbol-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.symbol === symbol);
    });
  }

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onMarketChange(market) {
    // Actualizar indicador de conexión
    this._updateConnectionStatus(market.connected);

    // Actualizar precio del tick
    if (market.lastTick) {
      this._updatePrice(market.lastTick);
    }
  }

  _updateConnectionStatus(connected) {
    const dot = document.getElementById('conn-indicator');
    if (!dot) return;

    if (connected) {
      dot.className = 'conn-dot connected';
      dot.title = 'Conectado';
    } else {
      dot.className = 'conn-dot disconnected';
      dot.title = 'Desconectado';
    }
  }

  _updatePrice(tick) {
    const { symbol, quote } = tick;
    
    const priceEl = document.getElementById(`price-${symbol}`);
    const deltaEl = document.getElementById(`delta-${symbol}`);
    
    if (!priceEl) return;

    priceEl.textContent = this._formatPrice(quote, symbol);

    // Delta (variación desde último tick)
    const prev = this._prevPrices[symbol];
    if (prev !== undefined && deltaEl) {
      const diff = quote - prev;
      const sign = diff > 0 ? '▲' : diff < 0 ? '▼' : '';
      
      deltaEl.textContent = sign;
      deltaEl.className = `symbol-delta ${diff > 0 ? 'up' : diff < 0 ? 'down' : ''}`;
    }

    this._prevPrices[symbol] = quote;

    // Efecto visual de actualización
    if (priceEl.parentElement) {
      priceEl.parentElement.classList.add('price-flash');
      setTimeout(() => {
        priceEl.parentElement?.classList.remove('price-flash');
      }, 200);
    }
  }

  // ─────────────────────────────────────────────────────────
  // Utilidades
  // ─────────────────────────────────────────────────────────

  _formatPrice(price, symbol) {
    if (price === null || price === undefined) return '--';
    
    // Formato según tipo de símbolo
    if (symbol?.includes('JPY')) {
      return price.toFixed(3);
    } else if (price > 1000) {
      return price.toFixed(2);
    } else if (price > 1) {
      return price.toFixed(4);
    }
    return price.toFixed(5);
  }

  render() {
    // No usado - actualizaciones directas al DOM
  }
}

export default SymbolSelector;
