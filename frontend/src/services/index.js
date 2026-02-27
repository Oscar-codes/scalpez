/**
 * QuantPulse – Services Index
 * =============================
 * Re-exporta todos los servicios.
 */

export { ApiService, ApiServiceClass } from './apiService.js';
export { WebSocketService, WebSocketServiceClass } from './websocketService.js';
export { AudioService, AudioServiceClass } from './audioService.js';

// Default exports
import ApiService from './apiService.js';
import WebSocketService from './websocketService.js';
import AudioService from './audioService.js';

export default {
  api: ApiService,
  ws: WebSocketService,
  audio: AudioService,
};
