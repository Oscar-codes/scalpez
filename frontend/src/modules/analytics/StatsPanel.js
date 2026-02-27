/**
 * QuantPulse – Stats Panel Component
 * =====================================
 * Panel de métricas cuantitativas de performance.
 * 
 * Extiende BaseComponent para gestión de lifecycle.
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';

// Definición de las tarjetas de métricas
const METRICS = [
  { id: 'total_trades',  label: 'Trades',        format: 'int',     icon: '📊' },
  { id: 'win_rate',      label: 'Win Rate',       format: 'pct',     icon: '🎯' },
  { id: 'profit_factor', label: 'Profit Factor',  format: 'dec4',    icon: '⚖️' },
  { id: 'expectancy',    label: 'Expectancy',     format: 'dec4pct', icon: '📈' },
  { id: 'avg_rr_real',   label: 'Avg RR Real',    format: 'dec2',    icon: '🔄' },
  { id: 'max_drawdown',  label: 'Max Drawdown',   format: 'dec4pct', icon: '📉' },
  { id: 'total_pnl',     label: 'Total PnL',      format: 'dec4pct', icon: '💰' },
  { id: 'avg_duration',  label: 'Avg Duration',   format: 'duration',icon: '⏱️' },
];

export class StatsPanel extends BaseComponent {
  constructor(containerId) {
    super(containerId);
    
    this._lastStats = null;
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    
    this._renderStructure();
    
    // Suscribirse a cambios de trading (stats)
    this.subscribeToStore('trading', (state) => this._onTradingChange(state));
    
    // Cargar stats iniciales
    const stats = Store.getState().trading?.stats;
    if (stats) this._updateStats(stats);
  }

  _renderStructure() {
    this.element.innerHTML = '';

    // Panel header
    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = `
      <span>Performance</span>
      <span id="stats-total" class="text-muted">0 trades</span>
    `;
    this.element.appendChild(header);

    // Panel body
    const body = document.createElement('div');
    body.className = 'panel-body';

    const grid = document.createElement('div');
    grid.className = 'stats-grid';

    METRICS.forEach(m => {
      const card = document.createElement('div');
      card.className = 'stat-card';
      card.id = `stat-${m.id}`;
      card.innerHTML = `
        <div class="stat-icon">${m.icon}</div>
        <div class="stat-body">
          <span class="stat-value" id="sv-${m.id}">--</span>
          <span class="stat-label">${m.label}</span>
        </div>
      `;
      grid.appendChild(card);
    });

    body.appendChild(grid);

    // Win/Loss counters row
    const counters = document.createElement('div');
    counters.className = 'stats-counters';
    counters.innerHTML = `
      <span class="counter-item profit" id="sv-wins">W: 0</span>
      <span class="counter-item loss" id="sv-losses">L: 0</span>
      <span class="counter-item muted" id="sv-expired">E: 0</span>
      <span class="counter-item" id="sv-gross">GP: 0 / GL: 0</span>
    `;
    body.appendChild(counters);

    this.element.appendChild(body);
  }

  // ─────────────────────────────────────────────────────────
  // State handlers
  // ─────────────────────────────────────────────────────────

  _onTradingChange(trading) {
    const stats = trading.stats;
    if (!stats || stats === this._lastStats) return;
    
    this._lastStats = stats;
    this._updateStats(stats);
  }

  _updateStats(stats) {
    const symbol = Store.getState().market?.currentSymbol;
    
    // Usar stats por símbolo si existen, sino globales
    const data = (stats.by_symbol && stats.by_symbol[symbol])
      ? stats.by_symbol[symbol]
      : stats.global || stats;

    // Actualizar header
    const totalEl = document.getElementById('stats-total');
    if (totalEl) {
      totalEl.textContent = `${data.total_trades || 0} trades`;
    }

    // Actualizar métricas
    METRICS.forEach(m => {
      const el = document.getElementById(`sv-${m.id}`);
      if (!el) return;
      
      const val = data[m.id];
      el.textContent = this._formatValue(val, m.format);
      
      // Colorear según valor
      this._colorizeValue(el, m.id, val);
    });

    // Actualizar contadores
    this._updateEl('sv-wins', `W: ${data.wins || 0}`);
    this._updateEl('sv-losses', `L: ${data.losses || 0}`);
    this._updateEl('sv-expired', `E: ${data.expired || 0}`);
    this._updateEl('sv-gross', 
      `GP: ${this._formatValue(data.gross_profit, 'dec4pct')} / ` +
      `GL: ${this._formatValue(data.gross_loss, 'dec4pct')}`
    );
  }

  _updateEl(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  // ─────────────────────────────────────────────────────────
  // Formateo
  // ─────────────────────────────────────────────────────────

  _formatValue(val, format) {
    if (val === null || val === undefined || isNaN(val)) return '--';

    switch (format) {
      case 'int':
        return Math.round(val).toString();
      case 'pct':
        return `${(val * 100).toFixed(1)}%`;
      case 'dec2':
        return val.toFixed(2);
      case 'dec4':
        return val.toFixed(4);
      case 'dec4pct':
        return `${val.toFixed(4)}%`;
      case 'duration':
        return this._formatDuration(val);
      default:
        return val.toString();
    }
  }

  _formatDuration(seconds) {
    if (!seconds || isNaN(seconds)) return '--';
    
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hrs}h ${mins}m`;
  }

  _colorizeValue(el, id, val) {
    // Quitar clases previas
    el.classList.remove('positive', 'negative', 'neutral');

    if (val === null || val === undefined) return;

    // Métricas donde positivo es bueno
    const positiveGood = ['win_rate', 'profit_factor', 'expectancy', 'total_pnl', 'avg_rr_real'];
    // Métricas donde negativo es malo
    const negativeIsBad = ['max_drawdown'];

    if (positiveGood.includes(id)) {
      if (val > 0) el.classList.add('positive');
      else if (val < 0) el.classList.add('negative');
    } else if (negativeIsBad.includes(id)) {
      if (val < 0) el.classList.add('negative');
    }
  }

  render() {
    // No usado - actualizaciones directas
  }
}

export default StatsPanel;
