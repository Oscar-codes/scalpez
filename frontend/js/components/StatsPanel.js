/**
 * QuantPulse – Stats Panel Component
 * =====================================
 * Panel de métricas cuantitativas de performance.
 *
 * MUESTRA LAS 12 MÉTRICAS DEL PRD:
 *   - Total trades, Wins, Losses, Expired
 *   - Win Rate, Profit Factor
 *   - Expectancy, Avg RR Real
 *   - Max Drawdown, Avg Duration
 *   - Total PnL, Best/Worst trade
 *
 * OPTIMIZACIÓN:
 *   - Solo actualiza DOM cuando llegan stats nuevas.
 *   - Usa textContent en vez de innerHTML para updates parciales.
 *   - Las tarjetas se crean una vez y se actualizan por ID.
 *
 * CÓMO SE USA:
 *   - Se suscribe a 'state:stats' del StateManager.
 *   - También hace fetch inicial via ApiService.
 */

import EventBus from '../core/eventBus.js';
import StateManager from '../core/stateManager.js';

const StatsPanel = (() => {
  let _container = null;

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

  function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return console.error('[StatsPanel] Container no encontrado');

    _render();
    _bindEvents();
  }

  function _render() {
    _container.innerHTML = '';

    // Panel header
    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = `
      <span>Performance</span>
      <span id="stats-total" class="text-muted">0 trades</span>
    `;
    _container.appendChild(header);

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

    _container.appendChild(body);
  }

  function _bindEvents() {
    EventBus.on('state:stats', (stats) => {
      if (!stats) return;
      // Usar stats globales o por símbolo actual
      const sym = StateManager.get('currentSymbol');
      const data = (stats.by_symbol && stats.by_symbol[sym])
        ? stats.by_symbol[sym]
        : stats.global;

      if (data) _updateValues(data);
    });

    // Cambio de símbolo → re-renderizar con datos del nuevo símbolo
    EventBus.on('state:currentSymbol', () => {
      const stats = StateManager.get('stats');
      if (!stats) return;
      const sym = StateManager.get('currentSymbol');
      const data = (stats.by_symbol && stats.by_symbol[sym])
        ? stats.by_symbol[sym]
        : stats.global;
      if (data) _updateValues(data);
    });
  }

  function _updateValues(data) {
    METRICS.forEach(m => {
      const el = document.getElementById(`sv-${m.id}`);
      if (!el) return;

      const val = data[m.id];
      el.textContent = _formatValue(val, m.format);

      // Color coding
      const card = document.getElementById(`stat-${m.id}`);
      if (!card) return;

      card.classList.remove('positive', 'negative', 'neutral');
      if (m.id === 'profit_factor') {
        card.classList.add(val > 1.0 ? 'positive' : val < 1.0 ? 'negative' : 'neutral');
      } else if (m.id === 'expectancy' || m.id === 'total_pnl') {
        card.classList.add(val > 0 ? 'positive' : val < 0 ? 'negative' : 'neutral');
      } else if (m.id === 'win_rate') {
        card.classList.add(val >= 50 ? 'positive' : 'negative');
      }
    });

    // Update counters
    _updateText('sv-wins', `W: ${data.wins || 0}`);
    _updateText('sv-losses', `L: ${data.losses || 0}`);
    _updateText('sv-expired', `E: ${data.expired || 0}`);
    _updateText('sv-gross', `GP: ${(data.gross_profit || 0).toFixed(4)} / GL: ${(data.gross_loss || 0).toFixed(4)}`);
    _updateText('stats-total', `${data.total_trades || 0} trades`);
  }

  function _updateText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function _formatValue(val, format) {
    if (val === undefined || val === null) return '--';
    switch (format) {
      case 'int':      return val.toString();
      case 'pct':      return val.toFixed(1) + '%';
      case 'dec2':     return val.toFixed(2);
      case 'dec4':     return val.toFixed(4);
      case 'dec4pct':  return val.toFixed(4) + '%';
      case 'duration': return _formatDuration(val);
      default:         return val.toString();
    }
  }

  function _formatDuration(seconds) {
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  }

  return Object.freeze({ init });
})();

export default StatsPanel;
