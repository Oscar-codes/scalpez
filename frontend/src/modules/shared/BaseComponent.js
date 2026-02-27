/**
 * QuantPulse – Base Component Class
 * ===================================
 * Clase base para todos los componentes UI.
 * Proporciona:
 *   - Suscripción al Store
 *   - Lifecycle hooks
 *   - Render scheduling
 *   - Cleanup automático
 *
 * USO:
 *   class MyComponent extends BaseComponent {
 *     constructor(elementId) {
 *       super(elementId);
 *       this.subscribeToStore('market', this.onMarketChange.bind(this));
 *     }
 *     
 *     render() {
 *       this.element.innerHTML = '...';
 *     }
 *   }
 */

import Store from '../../core/state/store.js';
import EventBus from '../../core/eventBus.js';

export class BaseComponent {
  /**
   * @param {string|HTMLElement} element - ID del elemento o el elemento mismo
   */
  constructor(element) {
    /** @type {HTMLElement|null} */
    this.element = typeof element === 'string' 
      ? document.getElementById(element) 
      : element;
    
    /** @type {Function[]} Cleanup functions */
    this._cleanups = [];
    
    /** @type {boolean} Render pendiente */
    this._renderPending = false;
    
    /** @type {number|null} RAF id */
    this._rafId = null;
    
    /** @type {boolean} Componente montado */
    this._mounted = false;
    
    if (!this.element) {
      console.warn(`[${this.constructor.name}] Elemento no encontrado`);
    }
  }

  /**
   * Suscribirse a un slice del Store.
   * @param {string} sliceName
   * @param {Function} callback
   */
  subscribeToStore(sliceName, callback) {
    const unsubscribe = Store.subscribe(sliceName, callback);
    this._cleanups.push(unsubscribe);
  }

  /**
   * Suscribirse a un evento del EventBus.
   * @param {string} event
   * @param {Function} callback
   */
  subscribeToEvent(event, callback) {
    const unsubscribe = EventBus.on(event, callback);
    this._cleanups.push(unsubscribe);
  }

  /**
   * Programar un render para el próximo frame.
   * Múltiples llamadas dentro del mismo frame se agrupan.
   */
  scheduleRender() {
    if (this._renderPending) return;
    this._renderPending = true;
    
    this._rafId = requestAnimationFrame(() => {
      this._renderPending = false;
      if (this._mounted) {
        this.render();
      }
    });
  }

  /**
   * Montar el componente.
   * Call this after setup to initialize.
   */
  mount() {
    if (this._mounted) return;
    this._mounted = true;
    
    if (this.onMount) {
      this.onMount();
    }
    
    this.scheduleRender();
  }

  /**
   * Desmontar el componente y limpiar recursos.
   */
  unmount() {
    if (!this._mounted) return;
    this._mounted = false;
    
    // Cancelar RAF pendiente
    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    
    // Ejecutar cleanups
    for (const cleanup of this._cleanups) {
      try {
        cleanup();
      } catch (e) {
        console.error(`[${this.constructor.name}] Error en cleanup:`, e);
      }
    }
    this._cleanups = [];
    
    if (this.onUnmount) {
      this.onUnmount();
    }
  }

  /**
   * Método de render - debe ser implementado por subclases.
   * @abstract
   */
  render() {
    // Override en subclases
  }

  /**
   * Hook llamado al montar - override opcional.
   */
  onMount() {
    // Override en subclases
  }

  /**
   * Hook llamado al desmontar - override opcional.
   */
  onUnmount() {
    // Override en subclases
  }

  /**
   * Helper para crear HTML seguro.
   * @param {string} html
   * @returns {DocumentFragment}
   */
  createFragment(html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content;
  }

  /**
   * Helper para establecer innerHTML de forma segura.
   * @param {string} html
   */
  setInnerHTML(html) {
    if (this.element) {
      this.element.innerHTML = html;
    }
  }

  /**
   * Helper para query selector dentro del componente.
   * @param {string} selector
   * @returns {HTMLElement|null}
   */
  $(selector) {
    return this.element?.querySelector(selector) || null;
  }

  /**
   * Helper para query selector all dentro del componente.
   * @param {string} selector
   * @returns {NodeList}
   */
  $$(selector) {
    return this.element?.querySelectorAll(selector) || [];
  }
}

export default BaseComponent;
