/**
 * QuantPulse – Trade Table Component
 * =====================================
 * Tabla de trades cerrados con render incremental.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { CONFIG } from '../../core/config.js';

export class TradeTable extends BaseComponent {
  constructor(containerId) {
    super(containerId);
    
    /** @type {HTMLTableSectionElement} */
    this._tbody = null;
    
    /** Set de IDs ya renderizados */
    this._renderedIds = new Set();
    
    /** Filtro de símbolo actual */
    this._filterSymbol = null;
    
    /** Filtro de resultado */
    this._filterStatus = null;
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    this._renderStructure();
    this._bindDOMEvents();
    
    // Suscribirse a cambios de estado
    this.subscribeToStore('trading', (state) => this._onTradingChange(state));
    
    // Cargar datos iniciales
    const trades = Store.getState().trading?.closedTrades || [];
    this._insertNewTrades(trades);
  }

  _renderStructure() {
    const symbols = CONFIG.DEFAULT_SYMBOLS;
    
    this.element.innerHTML = `
      <div class="trade-table-wrapper">
        <div class="trade-table-header">
          <h3>Historial de Trades</h3>
          <div class="trade-filters">
            <select id="trade-filter-symbol" class="form-select form-select-sm">
              <option value="">Todos</option>
              ${symbols.map(s => `<option value="${s}">${s}</option>`).join('')}
            </select>
            <select id="trade-filter-status" class="form-select form-select-sm">
              <option value="">Resultado</option>
              <option value="WIN">WIN</option>
              <option value="LOSS">LOSS</option>
              <option value="EXPIRED">EXPIRED</option>
            </select>
          </div>
        </div>
        <div class="trade-table-scroll">
          <table class="trade-table">
            <thead>
              <tr>
                <th>Hora</th>
                <th>Símbolo</th>
                <th>Tipo</th>
                <th>Entry</th>
                <th>Close</th>
                <th>Status</th>
                <th>PnL%</th>
                <th>Dur.</th>
                <th>Condiciones</th>
              </tr>
            </thead>
            <tbody id="trade-tbody"></tbody>
          </table>
        </div>
        <div class="trade-table-footer">
          <span id="trade-count" class="muted">0 trades</span>
        </div>
      </div>
    `;

    this._tbody = document.getElementById('trade-tbody');
  }

  _bindDOMEvents() {
    const symbolSelect = document.getElementById('trade-filter-symbol');
    if (symbolSelect) {
      symbolSelect.addEventListener('change', (e) => {
        this._filterSymbol = e.target.value || null;
        this._applyFilter();
      });
    }
    
    const statusSelect = document.getElementById('trade-filter-status');
    if (statusSelect) {
      statusSelect.addEventListener('change', (e) => {
        this._filterStatus = e.target.value || null;
        this._applyFilter();
      });
    }
  }

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onTradingChange(trading) {
    const trades = trading.closedTrades || [];
    this._insertNewTrades(trades);
  }

  // ─────────────────────────────────────────────────────────
  // Render incremental
  // ─────────────────────────────────────────────────────────

  _insertNewTrades(trades) {
    const fragment = document.createDocumentFragment();
    let newCount = 0;

    for (const trade of trades) {
      const id = trade.id || `${trade.symbol}_${trade.open_timestamp}`;
      
      if (this._renderedIds.has(id)) continue;
      this._renderedIds.add(id);

      const row = this._createTradeRow(trade, id);
      fragment.prepend(row); // Nuevos arriba
      newCount++;
    }

    if (newCount > 0 && this._tbody) {
      this._tbody.prepend(fragment);
      this._updateCount();
      
      // Limitar filas en DOM
      while (this._tbody.children.length > 100) {
        const lastRow = this._tbody.lastElementChild;
        if (lastRow) {
          this._renderedIds.delete(lastRow.dataset.tradeId);
          lastRow.remove();
        }
      }
    }
  }

  _createTradeRow(trade, id) {
    const row = document.createElement('tr');
    row.dataset.tradeId = id;
    row.dataset.symbol = trade.symbol;
    row.dataset.status = trade.status;

    const isWin = trade.status === 'WIN';
    const pnlClass = isWin ? 'positive' : (trade.status === 'LOSS' ? 'negative' : '');
    const statusClass = isWin ? 'status-win' : (trade.status === 'LOSS' ? 'status-loss' : 'status-expired');

    row.innerHTML = `
      <td>${this._formatTime(trade.close_timestamp || trade.open_timestamp)}</td>
      <td><span class="symbol-badge">${trade.symbol}</span></td>
      <td class="${trade.trade_type === 'BUY' ? 'text-success' : 'text-danger'}">${trade.trade_type}</td>
      <td>${this._formatPrice(trade.entry_price)}</td>
      <td>${this._formatPrice(trade.close_price)}</td>
      <td><span class="status-badge ${statusClass}">${trade.status}</span></td>
      <td class="${pnlClass}">${trade.pnl_percent?.toFixed(3) || '--'}%</td>
      <td>${this._formatDuration(trade.duration_seconds)}</td>
      <td class="conditions">${this._formatConditions(trade.conditions_met)}</td>
    `;

    // Aplicar filtros iniciales
    const passSymbol = !this._filterSymbol || trade.symbol === this._filterSymbol;
    const passStatus = !this._filterStatus || trade.status === this._filterStatus;
    if (!passSymbol || !passStatus) {
      row.style.display = 'none';
    }

    return row;
  }

  // ─────────────────────────────────────────────────────────
  // Filtrado
  // ─────────────────────────────────────────────────────────

  _applyFilter() {
    if (!this._tbody) return;

    const rows = this._tbody.querySelectorAll('tr');
    let visibleCount = 0;

    rows.forEach(row => {
      const symbol = row.dataset.symbol;
      const status = row.dataset.status;
      const passSymbol = !this._filterSymbol || symbol === this._filterSymbol;
      const passStatus = !this._filterStatus || status === this._filterStatus;
      const show = passSymbol && passStatus;
      row.style.display = show ? '' : 'none';
      if (show) visibleCount++;
    });

    this._updateCount(visibleCount);
  }

  _updateCount(count) {
    const el = document.getElementById('trade-count');
    if (el) {
      const total = this._renderedIds.size;
      if (count !== undefined && count !== total) {
        el.textContent = `${count} de ${total} trades`;
      } else {
        el.textContent = `${total} trades`;
      }
    }
  }

  // ─────────────────────────────────────────────────────────
  // Utilidades
  // ─────────────────────────────────────────────────────────

  _formatTime(timestamp) {
    if (!timestamp) return '--';
    const d = new Date(timestamp * 1000);
    return d.toLocaleTimeString();
  }

  _formatPrice(price) {
    if (price === null || price === undefined) return '--';
    if (price > 1000) return price.toFixed(2);
    if (price > 1) return price.toFixed(4);
    return price.toFixed(5);
  }

  _formatDuration(seconds) {
    if (!seconds) return '--';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  }

  _formatConditions(conditions) {
    if (!conditions || !Array.isArray(conditions)) return '--';
    if (conditions.length === 0) return '--';
    
    return conditions.slice(0, 3)
      .map(c => `<span class="condition-mini">${c}</span>`)
      .join(' ');
  }

  // ─────────────────────────────────────────────────────────
  // API pública
  // ─────────────────────────────────────────────────────────

  clear() {
    this._renderedIds.clear();
    if (this._tbody) {
      this._tbody.innerHTML = '';
    }
    this._updateCount();
  }

  render() {
    // No usado - render incremental
  }
}

export default TradeTable;
