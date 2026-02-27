/**
 * QuantPulse – Settings Panel Component
 * ========================================
 * Panel de configuración para parámetros de trading.
 * 
 * PARÁMETROS EDITABLES:
 *   - EMA rápida (default: 9)
 *   - EMA lenta (default: 21)
 *   - RSI periodo (default: 14)
 *   - RSI overbought/oversold
 *   - Risk:Reward ratio
 *   - Tiempo máximo de trade
 */

import { BaseComponent } from '../shared/BaseComponent.js';
import { Store } from '../../core/state/store.js';
import { CONFIG } from '../../core/config.js';
import { ApiService } from '../../services/apiService.js';

export class SettingsPanel extends BaseComponent {
  constructor(containerId) {
    super(containerId);
    
    this._settings = {
      ema_fast: CONFIG.EMA_FAST,
      ema_slow: CONFIG.EMA_SLOW,
      rsi_period: CONFIG.RSI_PERIOD,
      rsi_overbought: CONFIG.RSI_OVERBOUGHT,
      rsi_oversold: CONFIG.RSI_OVERSOLD,
      rr_ratio: CONFIG.DEFAULT_RR_RATIO,
      trade_expiry_minutes: CONFIG.TRADE_EXPIRY_MINUTES,
    };
    
    this._dirty = false;
  }

  // ─────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────

  mount() {
    super.mount();
    this._renderStructure();
    this._bindDOMEvents();
  }

  _renderStructure() {
    const s = this._settings;
    
    this.element.innerHTML = `
      <div class="settings-panel">
        <div class="settings-header">
          <h3>⚙️ Configuración</h3>
          <span class="settings-status" id="settings-status"></span>
        </div>
        
        <div class="settings-body">
          <!-- EMA Settings -->
          <div class="settings-section">
            <h4>Medias Móviles (EMA)</h4>
            <div class="settings-row">
              <label for="ema-fast">EMA Rápida:</label>
              <input type="number" id="ema-fast" value="${s.ema_fast}" min="3" max="50" class="form-input">
            </div>
            <div class="settings-row">
              <label for="ema-slow">EMA Lenta:</label>
              <input type="number" id="ema-slow" value="${s.ema_slow}" min="10" max="100" class="form-input">
            </div>
          </div>
          
          <!-- RSI Settings -->
          <div class="settings-section">
            <h4>RSI (Relative Strength Index)</h4>
            <div class="settings-row">
              <label for="rsi-period">Período:</label>
              <input type="number" id="rsi-period" value="${s.rsi_period}" min="7" max="28" class="form-input">
            </div>
            <div class="settings-row">
              <label for="rsi-overbought">Sobrecompra:</label>
              <input type="number" id="rsi-overbought" value="${s.rsi_overbought}" min="60" max="90" class="form-input">
            </div>
            <div class="settings-row">
              <label for="rsi-oversold">Sobreventa:</label>
              <input type="number" id="rsi-oversold" value="${s.rsi_oversold}" min="10" max="40" class="form-input">
            </div>
          </div>
          
          <!-- Risk Management -->
          <div class="settings-section">
            <h4>Gestión de Riesgo</h4>
            <div class="settings-row">
              <label for="rr-ratio">Risk:Reward:</label>
              <select id="rr-ratio" class="form-select">
                ${CONFIG.RR_OPTIONS.map(rr => 
                  `<option value="${rr}" ${rr === s.rr_ratio ? 'selected' : ''}>1:${rr}</option>`
                ).join('')}
              </select>
            </div>
            <div class="settings-row">
              <label for="trade-expiry">Expiración (min):</label>
              <input type="number" id="trade-expiry" value="${s.trade_expiry_minutes}" min="5" max="60" class="form-input">
            </div>
          </div>
        </div>
        
        <div class="settings-footer">
          <button id="btn-reset-settings" class="btn btn-secondary">Restaurar</button>
          <button id="btn-apply-settings" class="btn btn-primary">Aplicar</button>
        </div>
      </div>
    `;
  }

  _bindDOMEvents() {
    // Inputs de cambio
    const inputs = this.element.querySelectorAll('input, select');
    inputs.forEach(input => {
      input.addEventListener('change', () => this._markDirty());
    });
    
    // Botón aplicar
    const applyBtn = document.getElementById('btn-apply-settings');
    if (applyBtn) {
      applyBtn.addEventListener('click', () => this._applySettings());
    }
    
    // Botón restaurar
    const resetBtn = document.getElementById('btn-reset-settings');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => this._resetSettings());
    }
  }

  _markDirty() {
    this._dirty = true;
    const status = document.getElementById('settings-status');
    if (status) {
      status.textContent = '• Cambios sin guardar';
      status.className = 'settings-status unsaved';
    }
  }

  async _applySettings() {
    // Leer valores de los inputs
    const newSettings = {
      ema_fast: parseInt(document.getElementById('ema-fast')?.value) || CONFIG.EMA_FAST,
      ema_slow: parseInt(document.getElementById('ema-slow')?.value) || CONFIG.EMA_SLOW,
      rsi_period: parseInt(document.getElementById('rsi-period')?.value) || CONFIG.RSI_PERIOD,
      rsi_overbought: parseInt(document.getElementById('rsi-overbought')?.value) || CONFIG.RSI_OVERBOUGHT,
      rsi_oversold: parseInt(document.getElementById('rsi-oversold')?.value) || CONFIG.RSI_OVERSOLD,
      rr_ratio: parseFloat(document.getElementById('rr-ratio')?.value) || CONFIG.DEFAULT_RR_RATIO,
      trade_expiry_minutes: parseInt(document.getElementById('trade-expiry')?.value) || CONFIG.TRADE_EXPIRY_MINUTES,
    };
    
    // Validaciones básicas
    if (newSettings.ema_fast >= newSettings.ema_slow) {
      this._showError('EMA rápida debe ser menor que EMA lenta');
      return;
    }
    
    if (newSettings.rsi_oversold >= newSettings.rsi_overbought) {
      this._showError('RSI sobreventa debe ser menor que sobrecompra');
      return;
    }
    
    try {
      // Enviar al backend
      await ApiService.updateSettings(newSettings);
      
      this._settings = newSettings;
      this._dirty = false;
      
      // Actualizar estado global
      Store.setState('ui', { settings: newSettings });
      
      this._showSuccess('Configuración aplicada');
      
    } catch (error) {
      console.error('[Settings] Error applying:', error);
      this._showError('Error al aplicar configuración');
    }
  }

  _resetSettings() {
    this._settings = {
      ema_fast: CONFIG.EMA_FAST,
      ema_slow: CONFIG.EMA_SLOW,
      rsi_period: CONFIG.RSI_PERIOD,
      rsi_overbought: CONFIG.RSI_OVERBOUGHT,
      rsi_oversold: CONFIG.RSI_OVERSOLD,
      rr_ratio: CONFIG.DEFAULT_RR_RATIO,
      trade_expiry_minutes: CONFIG.TRADE_EXPIRY_MINUTES,
    };
    
    this._renderStructure();
    this._bindDOMEvents();
    this._dirty = false;
    
    this._showSuccess('Valores restaurados');
  }

  _showSuccess(message) {
    const status = document.getElementById('settings-status');
    if (status) {
      status.textContent = `✓ ${message}`;
      status.className = 'settings-status saved';
      setTimeout(() => {
        status.textContent = '';
      }, 3000);
    }
  }

  _showError(message) {
    const status = document.getElementById('settings-status');
    if (status) {
      status.textContent = `✗ ${message}`;
      status.className = 'settings-status error';
    }
  }

  render() {
    // No usado
  }
}

export default SettingsPanel;
