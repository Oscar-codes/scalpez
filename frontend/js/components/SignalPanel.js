/**
 * QuantPulse – Signal Panel Component
 * ======================================
 * Panel visual de la señal actual y trade activo.
 *
 * MUESTRA:
 *   - Tipo: BUY / SELL (grande, coloreado)
 *   - Entry, SL, TP, RR
 *   - Condiciones activadas (badges)
 *   - Trade activo: estado, PnL estimado, duración
 *
 * ACTUALIZACIÓN:
 *   - Se suscribe a 'state:activeSignal' → nueva señal
 *   - Se suscribe a 'state:activeTrades' → trade abierto/cerrado
 *   - Se suscribe a 'state:tick' → PnL estimado live
 *   - Solo muta el DOM cuando hay datos nuevos relevantes
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const SignalPanel = (() => {
  let _container = null;
  let _currentSignal = null;
  let _currentTrade = null;

  // ── Inicialización ────────────────────────────────────────────

  function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return console.error('[SignalPanel] Container no encontrado');

    _render();
    _bindEvents();
  }

  // ── Render inicial ────────────────────────────────────────────

  function _render() {
    _container.innerHTML = `
      <div class="signal-panel">
        <div class="signal-header">
          <h3>Señal Actual</h3>
          <span id="signal-time" class="signal-time">--</span>
        </div>
        <div id="signal-content" class="signal-content signal-empty">
          <span class="muted">Esperando señal...</span>
        </div>
        <div class="trade-section">
          <h4>Trade Activo</h4>
          <div id="trade-content" class="trade-content">
            <span class="muted">Sin trade activo</span>
          </div>
        </div>
      </div>
    `;
  }

  // ── Suscripciones ─────────────────────────────────────────────

  function _bindEvents() {
    EventBus.on('state:activeSignal', (signal) => {
      if (!signal) return;
      // Solo mostrar señales del símbolo actual
      if (signal.symbol !== StateManager.get('currentSymbol')) return;
      _currentSignal = signal;
      _renderSignal(signal);
    });

    EventBus.on('state:activeTrades', (trades) => {
      const sym = StateManager.get('currentSymbol');
      const trade = trades[sym] || null;
      _currentTrade = trade;
      _renderTrade(trade);
    });

    // PnL estimado en tiempo real (solo si hay trade abierto)
    EventBus.on('state:tick', (tick) => {
      if (!_currentTrade) return;
      if (tick.symbol !== _currentTrade.symbol) return;
      if (_currentTrade.status !== 'OPEN' && _currentTrade.status !== 'PENDING') return;
      _updateLivePnl(tick.quote);
    });

    // Cambio de símbolo → limpiar
    EventBus.on('state:currentSymbol', () => {
      _currentSignal = null;
      _currentTrade = null;
      _render();
    });
  }

  // ── Render de señal ───────────────────────────────────────────

  function _renderSignal(signal) {
    const el = document.getElementById('signal-content');
    if (!el) return;

    const isBuy = signal.signal_type === 'BUY';
    const typeClass = isBuy ? 'signal-buy' : 'signal-sell';

    el.className = 'signal-content';
    el.innerHTML = `
      <div class="signal-type ${typeClass}">
        ${signal.signal_type}
      </div>
      <div class="signal-details">
        <div class="signal-row">
          <span class="label">Entry</span>
          <span class="value">${_fmtPrice(signal.entry)}</span>
        </div>
        <div class="signal-row">
          <span class="label">Stop Loss</span>
          <span class="value sl">${_fmtPrice(signal.stop_loss)}</span>
        </div>
        <div class="signal-row">
          <span class="label">Take Profit</span>
          <span class="value tp">${_fmtPrice(signal.take_profit)}</span>
        </div>
        <div class="signal-row">
          <span class="label">R:R</span>
          <span class="value">${signal.rr.toFixed(1)}</span>
        </div>
      </div>
      <div class="signal-conditions">
        ${signal.conditions.map(c =>
          `<span class="badge badge-condition">${c}</span>`
        ).join('')}
      </div>
    `;

    // Timestamp
    const timeEl = document.getElementById('signal-time');
    if (timeEl) {
      const d = new Date(signal.timestamp * 1000);
      timeEl.textContent = d.toLocaleTimeString();
    }
  }

  // ── Render de trade activo ────────────────────────────────────

  function _renderTrade(trade) {
    const el = document.getElementById('trade-content');
    if (!el) return;

    if (!trade) {
      el.innerHTML = '<span class="muted">Sin trade activo</span>';
      return;
    }

    const statusClass = {
      PENDING: 'badge-warning',
      OPEN: 'badge-info',
      PROFIT: 'badge-profit',
      LOSS: 'badge-loss',
      EXPIRED: 'badge-muted',
    }[trade.status] || 'badge-muted';

    el.innerHTML = `
      <div class="trade-row">
        <span class="label">Estado</span>
        <span class="badge ${statusClass}">${trade.status}</span>
      </div>
      <div class="trade-row">
        <span class="label">Tipo</span>
        <span class="value">${trade.signal_type}</span>
      </div>
      <div class="trade-row">
        <span class="label">Entry</span>
        <span class="value">${_fmtPrice(trade.entry_price || trade.signal_entry)}</span>
      </div>
      <div class="trade-row">
        <span class="label">SL / TP</span>
        <span class="value">
          <span class="sl">${_fmtPrice(trade.stop_loss)}</span> /
          <span class="tp">${_fmtPrice(trade.take_profit)}</span>
        </span>
      </div>
      <div class="trade-row" id="live-pnl-row">
        <span class="label">PnL est.</span>
        <span class="value" id="live-pnl">--</span>
      </div>
    `;
  }

  function _updateLivePnl(currentPrice) {
    const el = document.getElementById('live-pnl');
    if (!el || !_currentTrade || !_currentTrade.entry_price) return;

    const entry = _currentTrade.entry_price;
    let pnl;
    if (_currentTrade.signal_type === 'BUY') {
      pnl = ((currentPrice - entry) / entry) * 100;
    } else {
      pnl = ((entry - currentPrice) / entry) * 100;
    }

    const cls = pnl >= 0 ? 'profit' : 'loss';
    el.textContent = `${pnl >= 0 ? '+' : ''}${pnl.toFixed(4)}%`;
    el.className = `value ${cls}`;
  }

  // ── Helpers ───────────────────────────────────────────────────

  function _fmtPrice(p) {
    if (!p) return '--';
    if (p > 10000) return p.toFixed(2);
    if (p > 100) return p.toFixed(2);
    return p.toFixed(5);
  }

  return Object.freeze({ init });
})();

export default SignalPanel;
