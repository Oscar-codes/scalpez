/**
 * QuantPulse – Trade Table Component
 * =====================================
 * Tabla responsive de trades cerrados con render incremental.
 *
 * OPTIMIZACIÓN:
 *   - Render incremental: solo inserta filas NUEVAS, no re-dibuja todo.
 *   - Usa DocumentFragment para batch inserts.
 *   - Scroll interno (max-height) sin paginar la página entera.
 *   - Filtro por símbolo con debounce.
 *   - Máximo 100 trades en memoria.
 *
 * CÓMO SE EVITA RE-RENDER COMPLETO:
 *   - Se mantiene un Set de trade IDs ya renderizados.
 *   - Cuando llega 'state:tradeHistory', solo se insertan los nuevos.
 *   - Al cambiar símbolo, se re-filtra la tabla existente (display:none).
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const TradeTable = (() => {
  let _container = null;
  let _tbody = null;

  /** Set de IDs ya renderizados para evitar duplicados */
  const _renderedIds = new Set();

  /** Filtro actual */
  let _filterSymbol = null;  // null = todos

  function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return console.error('[TradeTable] Container no encontrado');

    _render();
    _bindEvents();
  }

  function _render() {
    _container.innerHTML = `
      <div class="trade-table-wrapper">
        <div class="trade-table-header">
          <h3>Historial de Trades</h3>
          <div class="trade-filters">
            <select id="trade-filter-symbol" class="form-select form-select-sm">
              <option value="">Todos</option>
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

    _tbody = document.getElementById('trade-tbody');

    // Popular selector de símbolos
    const select = document.getElementById('trade-filter-symbol');
    StateManager.get('symbols').forEach(sym => {
      const opt = document.createElement('option');
      opt.value = sym;
      opt.textContent = sym;
      select.appendChild(opt);
    });

    select.addEventListener('change', (e) => {
      _filterSymbol = e.target.value || null;
      _applyFilter();
    });
  }

  function _bindEvents() {
    // Nuevo trade cerrado → insertar fila incremental
    EventBus.on('state:tradeHistory', (trades) => {
      _insertNewTrades(trades);
    });

    // Cambio de símbolo → re-filtrar (no re-render)
    EventBus.on('state:currentSymbol', () => {
      // No cambiar filtro automáticamente
    });
  }

  /**
   * Insertar solo trades NUEVOS en la tabla.
   * Usa DocumentFragment para batch insert eficiente.
   */
  function _insertNewTrades(trades) {
    if (!_tbody) return;

    const fragment = document.createDocumentFragment();
    let newCount = 0;

    for (const trade of trades) {
      if (_renderedIds.has(trade.id)) continue;
      _renderedIds.add(trade.id);

      const row = _createRow(trade);
      fragment.appendChild(row);
      newCount++;
    }

    if (newCount > 0) {
      // Insertar al inicio (los más recientes primero)
      _tbody.prepend(fragment);

      // Limitar filas en DOM (max 100)
      while (_tbody.children.length > 100) {
        const last = _tbody.lastElementChild;
        if (last) {
          _renderedIds.delete(last.dataset.tradeId);
          _tbody.removeChild(last);
        }
      }

      _applyFilter();
      _updateCount();
    }
  }

  function _createRow(trade) {
    const tr = document.createElement('tr');
    tr.dataset.tradeId = trade.id;
    tr.dataset.symbol = trade.symbol;

    const statusCls = {
      PROFIT: 'profit', LOSS: 'loss', EXPIRED: 'muted',
    }[trade.status] || '';

    const pnl = trade.pnl_percent;
    const pnlCls = pnl > 0 ? 'profit' : pnl < 0 ? 'loss' : 'muted';
    const pnlStr = pnl !== null ? `${pnl > 0 ? '+' : ''}${pnl.toFixed(4)}%` : '--';

    const dur = trade.duration_seconds;
    const durStr = dur !== null
      ? (dur < 60 ? `${dur.toFixed(0)}s` : `${Math.floor(dur / 60)}m ${Math.floor(dur % 60)}s`)
      : '--';

    const time = trade.close_timestamp
      ? new Date(trade.close_timestamp * 1000).toLocaleTimeString()
      : '--';

    tr.innerHTML = `
      <td class="mono">${time}</td>
      <td>${trade.symbol}</td>
      <td class="${trade.signal_type === 'BUY' ? 'profit' : 'loss'}">${trade.signal_type}</td>
      <td class="mono">${_fmtPrice(trade.entry_price)}</td>
      <td class="mono">${_fmtPrice(trade.close_price)}</td>
      <td><span class="badge badge-${statusCls}">${trade.status}</span></td>
      <td class="mono ${pnlCls}">${pnlStr}</td>
      <td class="mono">${durStr}</td>
      <td>${(trade.conditions || []).map(c => `<span class="badge badge-condition">${c}</span>`).join(' ')}</td>
    `;

    return tr;
  }

  function _applyFilter() {
    if (!_tbody) return;
    const rows = _tbody.querySelectorAll('tr');
    rows.forEach(row => {
      if (!_filterSymbol || row.dataset.symbol === _filterSymbol) {
        row.style.display = '';
      } else {
        row.style.display = 'none';
      }
    });
    _updateCount();
  }

  function _updateCount() {
    const el = document.getElementById('trade-count');
    if (!el || !_tbody) return;
    const visible = _tbody.querySelectorAll('tr:not([style*="display: none"])').length;
    el.textContent = `${visible} trade${visible !== 1 ? 's' : ''}`;
  }

  function _fmtPrice(p) {
    if (!p) return '--';
    if (p > 10000) return p.toFixed(2);
    if (p > 100) return p.toFixed(2);
    return p.toFixed(5);
  }

  return Object.freeze({ init });
})();

export default TradeTable;
