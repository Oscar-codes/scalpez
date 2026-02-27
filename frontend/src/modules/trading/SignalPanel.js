/**
 * QuantPulse – Signal Panel Component
 * ======================================
 * Panel visual de la señal actual y trade activo.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';

export class SignalPanel extends BaseComponent {
  constructor(containerId) {
    super(containerId);
    
    this._currentSignal = null;
    this._currentTrade = null;
    this._lastTick = null;
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    // Render inicial
    this._renderStructure();
    
    // Suscribirse a cambios de estado
    this.subscribeToStore('trading', (state) => this._onTradingChange(state));
    this.subscribeToStore('market', (state) => this._onMarketChange(state));
  }

  _renderStructure() {
    this.element.innerHTML = `
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

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onTradingChange(trading) {
    const symbol = Store.getState().market?.currentSymbol;
    
    // Señales
    const signals = trading.signals || [];
    const lastSignal = signals.filter(s => s.symbol === symbol).pop();
    
    if (lastSignal && lastSignal !== this._currentSignal) {
      this._currentSignal = lastSignal;
      this._renderSignal(lastSignal);
    }
    
    // Trade activo
    const openTrades = trading.openTrades || [];
    const activeTrade = openTrades.find(t => t.symbol === symbol);
    
    if (activeTrade !== this._currentTrade) {
      this._currentTrade = activeTrade || null;
      this._renderTrade(this._currentTrade);
    }
  }

  _onMarketChange(market) {
    // Actualizar PnL con último tick
    if (this._currentTrade && market.lastTick) {
      const tick = market.lastTick;
      if (tick.symbol === this._currentTrade.symbol) {
        this._updateLivePnl(tick.quote);
      }
    }
    
    // Cambio de símbolo → resetear
    if (market.currentSymbol && this._currentSignal?.symbol !== market.currentSymbol) {
      this._currentSignal = null;
      this._currentTrade = null;
      this._renderStructure();
    }
  }

  // ─────────────────────────────────────────────────────────
  // Render de señal
  // ─────────────────────────────────────────────────────────

  _renderSignal(signal) {
    const el = document.getElementById('signal-content');
    if (!el) return;

    const isBuy = signal.signal_type === 'BUY';
    const typeClass = isBuy ? 'signal-buy' : 'signal-sell';
    const typeIcon = isBuy ? '▲' : '▼';

    el.className = `signal-content ${typeClass}`;
    el.innerHTML = `
      <div class="signal-type ${typeClass}">
        <span class="signal-icon">${typeIcon}</span>
        <span class="signal-label">${signal.signal_type}</span>
      </div>
      <div class="signal-details">
        <div class="signal-row">
          <span class="label">Entry:</span>
          <span class="value">${this._formatPrice(signal.entry_price)}</span>
        </div>
        <div class="signal-row">
          <span class="label">SL:</span>
          <span class="value sl">${this._formatPrice(signal.stop_loss)}</span>
        </div>
        <div class="signal-row">
          <span class="label">TP:</span>
          <span class="value tp">${this._formatPrice(signal.take_profit)}</span>
        </div>
        <div class="signal-row">
          <span class="label">RR:</span>
          <span class="value">${signal.risk_reward?.toFixed(2) || '--'}</span>
        </div>
      </div>
      <div class="signal-conditions">
        ${this._renderConditions(signal.conditions_met)}
      </div>
    `;

    // Actualizar tiempo
    const timeEl = document.getElementById('signal-time');
    if (timeEl) {
      timeEl.textContent = this._formatTime(signal.timestamp);
    }
  }

  _renderConditions(conditions) {
    if (!conditions || !Array.isArray(conditions)) return '';
    
    return conditions.map(c => `
      <span class="condition-badge">${c}</span>
    `).join('');
  }

  // ─────────────────────────────────────────────────────────
  // Render de trade
  // ─────────────────────────────────────────────────────────

  _renderTrade(trade) {
    const el = document.getElementById('trade-content');
    if (!el) return;

    if (!trade) {
      el.innerHTML = '<span class="muted">Sin trade activo</span>';
      return;
    }

    const statusClass = this._getStatusClass(trade.status);

    el.innerHTML = `
      <div class="trade-active ${statusClass}">
        <div class="trade-row">
          <span class="label">Estado:</span>
          <span class="value status ${statusClass}">${trade.status}</span>
        </div>
        <div class="trade-row">
          <span class="label">Tipo:</span>
          <span class="value">${trade.trade_type}</span>
        </div>
        <div class="trade-row">
          <span class="label">Entry:</span>
          <span class="value">${this._formatPrice(trade.entry_price)}</span>
        </div>
        <div class="trade-row">
          <span class="label">PnL:</span>
          <span class="value pnl" id="live-pnl">--</span>
        </div>
        <div class="trade-row">
          <span class="label">Duración:</span>
          <span class="value" id="trade-duration">${this._formatDuration(trade.open_timestamp)}</span>
        </div>
      </div>
    `;
  }

  _getStatusClass(status) {
    switch (status) {
      case 'OPEN':
        return 'status-open';
      case 'PENDING':
        return 'status-pending';
      case 'WIN':
        return 'status-win';
      case 'LOSS':
        return 'status-loss';
      default:
        return '';
    }
  }

  // ─────────────────────────────────────────────────────────
  // PnL en tiempo real
  // ─────────────────────────────────────────────────────────

  _updateLivePnl(currentPrice) {
    const pnlEl = document.getElementById('live-pnl');
    const durEl = document.getElementById('trade-duration');
    
    if (!pnlEl || !this._currentTrade) return;

    const entry = this._currentTrade.entry_price;
    const isBuy = this._currentTrade.trade_type === 'BUY';
    
    const pnlPct = isBuy
      ? ((currentPrice - entry) / entry) * 100
      : ((entry - currentPrice) / entry) * 100;

    pnlEl.textContent = `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(3)}%`;
    pnlEl.className = `value pnl ${pnlPct >= 0 ? 'positive' : 'negative'}`;

    // Actualizar duración
    if (durEl) {
      durEl.textContent = this._formatDuration(this._currentTrade.open_timestamp);
    }
  }

  // ─────────────────────────────────────────────────────────
  // Utilidades
  // ─────────────────────────────────────────────────────────

  _formatPrice(price) {
    if (price === null || price === undefined) return '--';
    if (price > 1000) return price.toFixed(2);
    if (price > 1) return price.toFixed(4);
    return price.toFixed(5);
  }

  _formatTime(timestamp) {
    if (!timestamp) return '--';
    const d = new Date(timestamp * 1000);
    return d.toLocaleTimeString();
  }

  _formatDuration(openTimestamp) {
    if (!openTimestamp) return '--';
    const now = Date.now() / 1000;
    const secs = Math.floor(now - openTimestamp);
    
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
    
    const hrs = Math.floor(secs / 3600);
    const mins = Math.floor((secs % 3600) / 60);
    return `${hrs}h ${mins}m`;
  }

  // ─────────────────────────────────────────────────────────
  // Render (override BaseComponent - no usado aquí)
  // ─────────────────────────────────────────────────────────

  render() {
    // Este componente usa renders específicos, no el método genérico
  }
}

export default SignalPanel;
