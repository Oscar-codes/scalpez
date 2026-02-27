/**
 * QuantPulse – App Orchestrator (Multi-Timeframe)
 * ==================================================
 * Punto de entrada del frontend. Conecta todos los módulos:
 *   - Core: EventBus, StateManager
 *   - Services: WebSocketService, ApiService
 *   - Components: SymbolSelector, TimeframeSelector, ChartComponent,
 *                 SignalPanel, StatsPanel, TradeTable, EquityCurve
 *
 * FLUJO DE ARRANQUE:
 *   1. Importar todos los módulos
 *   2. Registrar listeners WS → StateManager (wire-up)
 *   3. Inicializar componentes UI (mount en DOM)
 *   4. Fetch datos iniciales vía REST (TF candles + indicators)
 *   5. Conectar WebSocket
 *   6. Programar fetch periódico de stats
 *
 * WIRE-UP (WebSocket events → StateManager mutations):
 *   ws:tick           → StateManager.updateTick(data)
 *   ws:tf_candle      → filter by active TF → StateManager.addCandle(data)
 *   ws:tf_indicators  → filter by active TF → StateManager.updateIndicators(data)
 *   ws:signal         → StateManager.addSignal(data)
 *   ws:trade_opened   → StateManager.addTradeOpened(data)
 *   ws:trade_closed   → StateManager.addTradeClosed(data)
 */

// ── Imports ─────────────────────────────────────────────────────
import EventBus from './core/eventBus.js';
import StateManager from './core/stateManager.js';
import WebSocketService from './services/websocketService.js';
import ApiService from './services/apiService.js';
import SymbolSelector from './components/SymbolSelector.js';
import TimeframeSelector from './components/TimeframeSelector.js';
import ChartComponent from './components/ChartComponent.js';
import SignalPanel from './components/SignalPanel.js';
import StatsPanel from './components/StatsPanel.js';
import TradeTable from './components/TradeTable.js';
import EquityCurve from './components/EquityCurve.js';

// ── Constants ───────────────────────────────────────────────────
const STATS_POLL_INTERVAL = 15_000; // fetch stats cada 15s

// ══════════════════════════════════════════════════════════════════
//  AUDIO ALERT SYSTEM (Web Audio API — sin archivos externos)
// ══════════════════════════════════════════════════════════════════
let _audioCtx = null;

function _getAudioCtx() {
  if (!_audioCtx) {
    _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return _audioCtx;
}

/**
 * Emitir un tono corto. freq=Hz, duration=segundos, type=onda.
 */
function _beep(freq = 880, duration = 0.15, type = 'sine') {
  try {
    const ctx = _getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration);
  } catch (e) {
    // Audio puede fallar en algunos navegadores sin interacción previa
  }
}

/** Alerta para nueva señal (doble beep agudo) */
function alertSignal() {
  _beep(1200, 0.12, 'sine');
  setTimeout(() => _beep(1500, 0.12, 'sine'), 150);
}

/** Alerta para trade abierto (beep medio) */
function alertTradeOpened() {
  _beep(880, 0.18, 'triangle');
}

/** Alerta para trade cerrado — profit (beep ascendente) */
function alertTradeProfit() {
  _beep(800, 0.1, 'sine');
  setTimeout(() => _beep(1100, 0.1, 'sine'), 120);
  setTimeout(() => _beep(1400, 0.15, 'sine'), 240);
}

/** Alerta para trade cerrado — loss (beep descendente) */
function alertTradeLoss() {
  _beep(600, 0.15, 'square');
  setTimeout(() => _beep(400, 0.2, 'square'), 180);
}

// ── Wire-up: WS events → StateManager ──────────────────────────
function wireWebSocketToState() {
  EventBus.on('ws:tick', (data) => {
    StateManager.updateTick(data);
  });

  // TF candles: solo procesar las del timeframe activo
  EventBus.on('ws:tf_candle', (data) => {
    const activeTf = StateManager.get('activeTimeframe');
    if (data.timeframe !== activeTf) return;
    StateManager.addCandle(data);
  });

  // TF indicators: solo procesar los del timeframe activo
  EventBus.on('ws:tf_indicators', (data) => {
    const activeTf = StateManager.get('activeTimeframe');
    if (data.timeframe !== activeTf) return;
    StateManager.updateIndicators(data);
  });

  // Legacy 5s candle/indicators (ignorar — ahora usamos tf_candle/tf_indicators)
  // EventBus.on('ws:candle', ...);
  // EventBus.on('ws:indicators', ...);

  EventBus.on('ws:signal', (data) => {
    StateManager.addSignal(data);
    alertSignal();
  });

  EventBus.on('ws:trade_opened', (data) => {
    StateManager.addTradeOpened(data);
    alertTradeOpened();
  });

  EventBus.on('ws:trade_closed', (data) => {
    StateManager.addTradeClosed(data);
    // Audio: profit vs loss
    if (data.result === 'PROFIT') {
      alertTradeProfit();
    } else {
      alertTradeLoss();
    }
    // Refrescar stats tras cierre de trade
    fetchStats();
  });
}

// ── Inicializar componentes UI ──────────────────────────────────
function initComponents() {
  SymbolSelector.init('symbol-selector');
  TimeframeSelector.init('tf-selector', onTimeframeChange);
  ChartComponent.init('chart-canvas');
  SignalPanel.init('signal-panel');
  StatsPanel.init('stats-panel');
  TradeTable.init('trade-table');
  EquityCurve.init('equity-canvas');
}

// ── Fetch inicial de datos vía REST ─────────────────────────────
async function fetchInitialData() {
  const currentSymbol = StateManager.get('currentSymbol');
  const activeTf = StateManager.get('activeTimeframe');

  // Fetch en paralelo para todos los símbolos
  const promises = [];

  // TF Candles para el símbolo actual
  promises.push(
    ApiService.getTfCandles(currentSymbol, activeTf, 200).then(data => {
      if (data && Array.isArray(data)) {
        data.forEach(c => StateManager.addCandle(c));
      }
    })
  );

  // Indicadores del símbolo actual (por TF)
  promises.push(
    ApiService.getIndicators(currentSymbol, activeTf).then(data => {
      if (data) StateManager.updateIndicators(data);
    })
  );

  // Stats globales
  promises.push(fetchStats());

  // Trades activos
  promises.push(
    ApiService.getActiveTrades().then(data => {
      if (data && Array.isArray(data)) {
        data.forEach(t => StateManager.addTradeOpened(t));
      }
    })
  );

  // Historial de trades
  promises.push(
    ApiService.getTradeHistory(null, 50).then(data => {
      if (data && Array.isArray(data)) {
        data.forEach(t => StateManager.addTradeClosed(t));
      }
    })
  );

  // Señales recientes
  promises.push(
    ApiService.getRecentSignals(null, 5).then(data => {
      if (data && Array.isArray(data) && data.length > 0) {
        StateManager.addSignal(data[0]);
      }
    })
  );

  // Sincronizar TF activo del servidor
  promises.push(
    ApiService.getTimeframe().then(data => {
      if (data && data.active) {
        StateManager.setActiveTimeframe(data.active);
      }
    })
  );

  await Promise.allSettled(promises);
  console.log('[App] Datos iniciales cargados');

  // Actualizar chart label con TF activo
  const label = document.getElementById('chart-label');
  if (label) label.textContent = `Candlestick · ${StateManager.get('activeTimeframe')}`;
}

// ── Fetch stats ─────────────────────────────────────────────────
async function fetchStats() {
  const data = await ApiService.getStats();
  if (data) {
    StateManager.updateStats(data);
  }
}

// ── Fetch periódico de stats ────────────────────────────────────
let _statsInterval = null;

function startStatsPoll() {
  if (_statsInterval) clearInterval(_statsInterval);
  _statsInterval = setInterval(fetchStats, STATS_POLL_INTERVAL);
}

// ── Listener para cambio de símbolo: refetch datos ──────────────
function onSymbolChange(symbol) {
  console.log(`[App] Símbolo cambiado a: ${symbol}`);
  const activeTf = StateManager.get('activeTimeframe');

  // Cargar TF candles e indicadores del nuevo símbolo si no existen
  const candles = StateManager.get('candles');
  if (!candles[symbol] || candles[symbol].length === 0) {
    ApiService.getTfCandles(symbol, activeTf, 200).then(data => {
      if (data && Array.isArray(data)) {
        data.forEach(c => StateManager.addCandle(c));
      }
    });
  }

  ApiService.getIndicators(symbol, activeTf).then(data => {
    if (data) StateManager.updateIndicators(data);
  });
}

// ── Listener para cambio de timeframe: POST + refetch ───────────
async function onTimeframeChange(tf) {
  console.log(`[App] Timeframe cambiado a: ${tf}`);

  // 1. Notificar servidor (cambia active_timeframe para signals)
  await ApiService.setTimeframe(tf);

  // 2. Actualizar estado local (limpia candles/indicators cache)
  StateManager.setActiveTimeframe(tf);

  // 3. Refetch candles e indicadores para todos los símbolos activos
  const currentSymbol = StateManager.get('currentSymbol');

  const [candlesData, indicatorsData] = await Promise.allSettled([
    ApiService.getTfCandles(currentSymbol, tf, 200),
    ApiService.getIndicators(currentSymbol, tf),
  ]);

  if (candlesData.status === 'fulfilled' && candlesData.value && Array.isArray(candlesData.value)) {
    candlesData.value.forEach(c => StateManager.addCandle(c));
  }

  if (indicatorsData.status === 'fulfilled' && indicatorsData.value) {
    StateManager.updateIndicators(indicatorsData.value);
  }

  console.log(`[App] Timeframe ${tf} — datos cargados`);
}

// ── Bootup ──────────────────────────────────────────────────────
async function boot() {
  console.log('[App] QuantPulse Dashboard v0.8 (Multi-Timeframe) — Iniciando...');

  // 1. Wire-up WS → State
  wireWebSocketToState();

  // 2. Escuchar cambio de símbolo
  EventBus.on('state:currentSymbol', onSymbolChange);

  // 3. Inicializar componentes UI
  initComponents();

  // 3b. Activar AudioContext al primer click (política de navegadores)
  const resumeAudio = () => {
    if (_audioCtx && _audioCtx.state === 'suspended') {
      _audioCtx.resume();
    }
    document.removeEventListener('click', resumeAudio);
  };
  document.addEventListener('click', resumeAudio);

  // 4. Conectar WebSocket (inicia reconexión automática)
  WebSocketService.connect();

  // 5. Fetch datos iniciales (no bloquea; WS irá actualizando)
  await fetchInitialData();

  // 6. Stats polling periódico
  startStatsPoll();

  console.log('[App] QuantPulse Dashboard listo ✓');
}

// ── Ejecutar al cargar DOM ──────────────────────────────────────
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
