-- ═══════════════════════════════════════════════════════════════════════════
-- QuantPulse – Initial Database Schema (MySQL 8.0+)
-- ═══════════════════════════════════════════════════════════════════════════
-- 
-- OBJETIVO:
--   Crear un esquema optimizado para trading algorítmico con preparación
--   completa para Machine Learning (Fase 8).
--
-- DECISIONES DE DISEÑO:
--
--   1. DECIMAL vs FLOAT:
--      - Precios, PnL, métricas → DECIMAL(20,8) para precisión exacta.
--      - Evita errores de redondeo acumulativos en millones de trades.
--      - Los índices sintéticos de Deriv tienen hasta 5-6 decimales.
--
--   2. BIGINT para IDs:
--      - Preparado para >4 mil millones de registros.
--      - AUTO_INCREMENT con row compression en InnoDB escala mejor.
--
--   3. TIMESTAMP vs DATETIME:
--      - TIMESTAMP para created_at (auto UTC, timezone-aware).
--      - BIGINT epoch_ms para timestamps de trading (precisión milisegundo).
--
--   4. ENUM vs VARCHAR:
--      - ENUMs para estados fijos (BUY/SELL, PROFIT/LOSS/EXPIRED).
--      - Menor almacenamiento (1-2 bytes vs N bytes).
--      - Validación a nivel de BD.
--
--   5. ÍNDICES COMPUESTOS:
--      - (symbol_id, created_at) para queries por símbolo + rango temporal.
--      - Cubre el 90% de queries analíticos.
--
--   6. trade_features SEPARADA:
--      - Normalización → trades no se inflan con columnas ML.
--      - Extensible → nuevos features sin ALTER TABLE masivos.
--      - Dataset supervisado: JOIN con trades WHERE status IN (PROFIT, LOSS).
--
-- ═══════════════════════════════════════════════════════════════════════════

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ───────────────────────────────────────────────────────────────────────────
-- 1) SYMBOLS: Catálogo de instrumentos
-- ───────────────────────────────────────────────────────────────────────────
-- 
-- Esta tabla es pequeña pero crucial:
--   - Normaliza el nombre del símbolo (ahorra bytes en signals/trades).
--   - Permite agregar metadata futura (horarios, spread típico, etc.).
--   - FK constraints garantizan integridad referencial.

DROP TABLE IF EXISTS `symbols`;
CREATE TABLE `symbols` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(32) NOT NULL COMMENT 'Deriv symbol ID (e.g., R_100, stpRNG)',
  `display_name` VARCHAR(64) NOT NULL COMMENT 'Nombre legible (e.g., Volatility 100)',
  `description` VARCHAR(255) DEFAULT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Si está habilitado para trading',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_symbols_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Catálogo de símbolos/instrumentos de Deriv';

-- Insertar símbolos iniciales
INSERT INTO `symbols` (`name`, `display_name`, `description`) VALUES
  ('stpRNG', 'Step Index', 'Índice sintético con steps regulares'),
  ('R_100', 'Volatility 100 (1s)', 'Alta volatilidad, ticks cada 1s'),
  ('R_75', 'Volatility 75', 'Volatilidad media-alta'),
  ('R_10', 'Volatility 10', 'Baja volatilidad');


-- ───────────────────────────────────────────────────────────────────────────
-- 2) SIGNALS: Historial completo de señales generadas
-- ───────────────────────────────────────────────────────────────────────────
--
-- CADA FILA = una señal BUY/SELL emitida por SignalEngine.
--
-- CAMPOS CLAVE PARA ML:
--   - ema9, ema21, rsi → Features numéricas directas
--   - pattern_detected → Feature categórica (one-hot encoding)
--   - support_level, resistance_level → Contexto estructural
--
-- POR QUÉ GUARDAR INDICADORES:
--   En producción, los indicadores se calculan en tiempo real y se
--   descartan. Al persistirlos, podemos:
--   1. Auditar qué vio el motor al generar la señal.
--   2. Entrenar modelos con features exactas del momento de decisión.
--   3. Detectar drift en distribución de features.

DROP TABLE IF EXISTS `signals`;
CREATE TABLE `signals` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `uuid` CHAR(12) NOT NULL COMMENT 'UUID corto generado por el sistema',
  `symbol_id` INT UNSIGNED NOT NULL,
  `signal_type` ENUM('BUY', 'SELL') NOT NULL,
  
  -- Precios de gestión de riesgo
  `entry_price` DECIMAL(20,8) NOT NULL COMMENT 'Precio de entrada sugerido',
  `stop_loss` DECIMAL(20,8) NOT NULL,
  `take_profit` DECIMAL(20,8) NOT NULL,
  `rr` DECIMAL(6,3) NOT NULL COMMENT 'Risk-Reward ratio calculado',
  
  -- Indicadores técnicos al momento de la señal
  `ema9` DECIMAL(20,8) DEFAULT NULL,
  `ema21` DECIMAL(20,8) DEFAULT NULL,
  `rsi` DECIMAL(6,3) DEFAULT NULL COMMENT 'RSI 14 (0-100)',
  
  -- Contexto estructural
  `pattern_detected` VARCHAR(64) DEFAULT NULL COMMENT 'Patrón detectado (ema_cross, sr_bounce, etc.)',
  `conditions` JSON NOT NULL COMMENT 'Array de condiciones que activaron la señal',
  `confidence` TINYINT UNSIGNED NOT NULL COMMENT 'Número de condiciones confirmadas (2-5)',
  `support_level` DECIMAL(20,8) DEFAULT NULL,
  `resistance_level` DECIMAL(20,8) DEFAULT NULL,
  
  -- Timeframe y timing
  `timeframe` VARCHAR(8) NOT NULL DEFAULT '5s' COMMENT 'Timeframe de la vela (5s, 1m, 5m)',
  `estimated_duration` INT UNSIGNED DEFAULT 0 COMMENT 'Duración estimada en segundos',
  `candle_timestamp` BIGINT UNSIGNED NOT NULL COMMENT 'Epoch ms de la vela confirmante',
  `created_at` TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_signals_uuid` (`uuid`),
  KEY `idx_signals_symbol_time` (`symbol_id`, `created_at`),
  KEY `idx_signals_type_time` (`signal_type`, `created_at`),
  KEY `idx_signals_timeframe` (`timeframe`, `created_at`),
  CONSTRAINT `fk_signals_symbol` FOREIGN KEY (`symbol_id`) 
    REFERENCES `symbols` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historial de señales de trading generadas';


-- ───────────────────────────────────────────────────────────────────────────
-- 3) TRADES: Historial completo de trades simulados
-- ───────────────────────────────────────────────────────────────────────────
--
-- CADA FILA = un trade de paper trading con su resultado.
--
-- RELACIÓN CON signals:
--   trades.signal_id → signals.id (1:1 típicamente, pero puede haber
--   señales sin trade si ya había uno activo).
--
-- CAMPOS CRÍTICOS:
--   - entry_price: Precio REAL de ejecución (puede diferir de signal.entry)
--   - pnl_percent: Normalizado, comparable entre símbolos
--   - rr_real: RR efectivamente obtenido (puede diferir del planeado)

DROP TABLE IF EXISTS `trades`;
CREATE TABLE `trades` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `uuid` CHAR(12) NOT NULL COMMENT 'UUID corto generado por el sistema',
  `signal_id` BIGINT UNSIGNED NOT NULL,
  `symbol_id` INT UNSIGNED NOT NULL,
  
  -- Precios
  `entry_price` DECIMAL(20,8) NOT NULL COMMENT 'Precio real de entrada (del tick)',
  `stop_loss` DECIMAL(20,8) NOT NULL,
  `take_profit` DECIMAL(20,8) NOT NULL,
  `close_price` DECIMAL(20,8) DEFAULT NULL COMMENT 'Precio de cierre (NULL si OPEN)',
  
  -- Resultado
  `status` ENUM('PENDING', 'OPEN', 'PROFIT', 'LOSS', 'EXPIRED') NOT NULL DEFAULT 'PENDING',
  `pnl_percent` DECIMAL(10,5) DEFAULT NULL COMMENT 'PnL normalizado en %',
  `rr_real` DECIMAL(6,3) DEFAULT NULL COMMENT 'RR real obtenido',
  
  -- Timing (epoch ms para precisión)
  `duration_seconds` INT UNSIGNED DEFAULT NULL,
  `opened_at` BIGINT UNSIGNED DEFAULT NULL COMMENT 'Epoch ms de apertura',
  `closed_at` BIGINT UNSIGNED DEFAULT NULL COMMENT 'Epoch ms de cierre',
  `created_at` TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_trades_uuid` (`uuid`),
  KEY `idx_trades_symbol_status` (`symbol_id`, `status`),
  KEY `idx_trades_status_time` (`status`, `created_at`),
  KEY `idx_trades_opened` (`opened_at`),
  KEY `idx_trades_signal` (`signal_id`),
  CONSTRAINT `fk_trades_signal` FOREIGN KEY (`signal_id`) 
    REFERENCES `signals` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_trades_symbol` FOREIGN KEY (`symbol_id`) 
    REFERENCES `symbols` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historial de trades simulados con paper trading';


-- ───────────────────────────────────────────────────────────────────────────
-- 4) TRADE_FEATURES: Dataset para Machine Learning
-- ───────────────────────────────────────────────────────────────────────────
--
-- ═══════════════════════════════════════════════════════════════════════════
-- POR QUÉ ESTA TABLA ES CRUCIAL PARA ML:
-- ═══════════════════════════════════════════════════════════════════════════
--
-- PROBLEMA DEL ML EN TRADING:
--   Para entrenar un modelo supervisado necesitamos:
--   X = features del momento de entrada
--   y = resultado del trade (PROFIT=1, LOSS=0)
--
--   Pero los indicadores en memoria se sobrescriben cada tick.
--   Sin persistencia, perdemos el contexto exacto de cada decisión.
--
-- SOLUCIÓN:
--   trade_features captura el SNAPSHOT EXACTO del mercado al momento
--   de entrada. Es el "antes" que permitirá predecir el "después".
--
-- CÓMO CREAR DATASET SUPERVISADO:
-- ───────────────────────────────
--   SELECT 
--     tf.*,
--     CASE WHEN t.status = 'PROFIT' THEN 1 ELSE 0 END AS label
--   FROM trade_features tf
--   JOIN trades t ON t.id = tf.trade_id
--   WHERE t.status IN ('PROFIT', 'LOSS')  -- Solo trades resueltos
--   ORDER BY t.opened_at;
--
-- FEATURES DISEÑADAS:
-- ───────────────────
--   - ema_distance: Distancia normalizada entre EMAs (momentum)
--   - rsi_value: RSI al momento de entrada
--   - rsi_slope: Derivada del RSI (acelerando/desacelerando)
--   - volatility_20: ATR de 20 períodos (régimen de volatilidad)
--   - candle_body_ratio: Body/Range de la vela (fuerza de la señal)
--   - pattern_type: Tipo de patrón (categórica → one-hot)
--   - distance_to_support/resistance: Contexto estructural
--   - market_structure_score: Higher highs/lows compuesto
--   - spread_estimate: Spread estimado (costo implícito)
--
-- EXTENSIBILIDAD:
--   Nuevos features → ALTER TABLE ADD COLUMN
--   No afecta tabla trades (separación de concerns)

DROP TABLE IF EXISTS `trade_features`;
CREATE TABLE `trade_features` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `trade_id` BIGINT UNSIGNED NOT NULL,
  
  -- Momentum Features
  `ema_distance` DECIMAL(12,8) NOT NULL COMMENT '(EMA9-EMA21)/price normalizado',
  `ema_slope_fast` DECIMAL(12,8) DEFAULT NULL COMMENT 'Pendiente EMA9 (delta N velas)',
  `ema_slope_slow` DECIMAL(12,8) DEFAULT NULL COMMENT 'Pendiente EMA21',
  
  -- RSI Features
  `rsi_value` DECIMAL(6,3) NOT NULL COMMENT 'RSI 14 (0-100)',
  `rsi_slope` DECIMAL(8,5) DEFAULT NULL COMMENT 'RSI actual - RSI anterior',
  `rsi_zone` ENUM('OVERSOLD', 'NEUTRAL', 'OVERBOUGHT') NOT NULL,
  
  -- Volatility Features
  `volatility_20` DECIMAL(16,8) DEFAULT NULL COMMENT 'ATR 20 períodos',
  `volatility_ratio` DECIMAL(8,5) DEFAULT NULL COMMENT 'Volatilidad actual / promedio',
  
  -- Candle Features
  `candle_body_ratio` DECIMAL(6,4) NOT NULL COMMENT 'abs(close-open)/range (0-1)',
  `candle_direction` ENUM('BULLISH', 'BEARISH', 'DOJI') NOT NULL,
  `candle_size_zscore` DECIMAL(8,4) DEFAULT NULL COMMENT 'Tamaño relativo (z-score)',
  
  -- Pattern & Structure
  `pattern_type` VARCHAR(32) NOT NULL COMMENT 'ema_cross, sr_bounce, breakout, etc.',
  `conditions_count` TINYINT UNSIGNED NOT NULL COMMENT 'Número de condiciones activas',
  
  -- Support/Resistance Context
  `distance_to_support` DECIMAL(12,8) DEFAULT NULL COMMENT '(price-support)/price',
  `distance_to_resistance` DECIMAL(12,8) DEFAULT NULL COMMENT '(resistance-price)/price',
  `sr_quality_score` DECIMAL(5,3) DEFAULT NULL COMMENT 'Fuerza del nivel S/R (0-1)',
  
  -- Market Structure
  `market_structure_score` DECIMAL(6,4) DEFAULT NULL COMMENT 'HH/HL ratio (-1 a +1)',
  `trend_alignment` ENUM('WITH_TREND', 'COUNTER_TREND', 'NEUTRAL') DEFAULT NULL,
  
  -- Execution Context
  `spread_estimate` DECIMAL(12,8) DEFAULT NULL COMMENT 'Spread estimado en el momento',
  `time_of_day_bucket` TINYINT UNSIGNED DEFAULT NULL COMMENT 'Hora del día (0-23)',
  `day_of_week` TINYINT UNSIGNED DEFAULT NULL COMMENT 'Día de semana (0-6)',
  
  -- ML Metadata
  `created_at` TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_trade_features_trade` (`trade_id`),
  KEY `idx_features_pattern` (`pattern_type`),
  KEY `idx_features_rsi` (`rsi_zone`, `rsi_value`),
  CONSTRAINT `fk_features_trade` FOREIGN KEY (`trade_id`) 
    REFERENCES `trades` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Features técnicas para ML - snapshot al momento de entrada';


-- ───────────────────────────────────────────────────────────────────────────
-- 5) PERFORMANCE_SNAPSHOTS: Métricas históricas para tracking
-- ───────────────────────────────────────────────────────────────────────────
--
-- Captura el estado de las métricas en puntos específicos del tiempo.
-- Útil para:
--   - Tracking de evolución del sistema
--   - Detección de degradación de performance
--   - Comparación entre períodos

DROP TABLE IF EXISTS `performance_snapshots`;
CREATE TABLE `performance_snapshots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `symbol_id` INT UNSIGNED DEFAULT NULL COMMENT 'NULL = métricas globales',
  `timeframe` VARCHAR(8) DEFAULT NULL COMMENT 'NULL = todos los TFs',
  
  -- Métricas principales
  `total_trades` INT UNSIGNED NOT NULL DEFAULT 0,
  `winning_trades` INT UNSIGNED NOT NULL DEFAULT 0,
  `losing_trades` INT UNSIGNED NOT NULL DEFAULT 0,
  `expired_trades` INT UNSIGNED NOT NULL DEFAULT 0,
  
  `win_rate` DECIMAL(6,3) DEFAULT NULL COMMENT 'Porcentaje 0-100',
  `profit_factor` DECIMAL(8,4) DEFAULT NULL COMMENT 'Gross profit / Gross loss',
  `expectancy` DECIMAL(10,5) DEFAULT NULL COMMENT 'E[PnL] por trade',
  
  `avg_win` DECIMAL(10,5) DEFAULT NULL COMMENT 'PnL% promedio en wins',
  `avg_loss` DECIMAL(10,5) DEFAULT NULL COMMENT 'PnL% promedio en losses (negativo)',
  `avg_rr_real` DECIMAL(6,3) DEFAULT NULL,
  
  `max_drawdown` DECIMAL(10,5) DEFAULT NULL COMMENT 'Máximo drawdown en %',
  `best_trade` DECIMAL(10,5) DEFAULT NULL,
  `worst_trade` DECIMAL(10,5) DEFAULT NULL,
  
  -- Equity tracking
  `cumulative_pnl` DECIMAL(12,5) DEFAULT NULL COMMENT 'PnL acumulado en %',
  `equity_curve` JSON DEFAULT NULL COMMENT 'Array de puntos para gráfico',
  
  -- Timing
  `period_start` TIMESTAMP DEFAULT NULL COMMENT 'Inicio del período medido',
  `period_end` TIMESTAMP DEFAULT NULL COMMENT 'Fin del período',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  PRIMARY KEY (`id`),
  KEY `idx_snapshots_symbol_time` (`symbol_id`, `created_at`),
  KEY `idx_snapshots_time` (`created_at`),
  CONSTRAINT `fk_snapshots_symbol` FOREIGN KEY (`symbol_id`) 
    REFERENCES `symbols` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Snapshots históricos de métricas de performance';


-- ───────────────────────────────────────────────────────────────────────────
-- 6) CANDLES: Historial de velas (opcional, para backtesting)
-- ───────────────────────────────────────────────────────────────────────────
--
-- Almacena velas cerradas para:
--   - Backtesting sin conexión a Deriv
--   - Entrenamiento de modelos con datos históricos
--   - Análisis de regímenes de mercado

DROP TABLE IF EXISTS `candles`;
CREATE TABLE `candles` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `symbol_id` INT UNSIGNED NOT NULL,
  `timeframe` VARCHAR(8) NOT NULL COMMENT '5s, 1m, 5m, etc.',
  
  `open` DECIMAL(20,8) NOT NULL,
  `high` DECIMAL(20,8) NOT NULL,
  `low` DECIMAL(20,8) NOT NULL,
  `close` DECIMAL(20,8) NOT NULL,
  `volume` BIGINT UNSIGNED DEFAULT 0,
  
  `timestamp` BIGINT UNSIGNED NOT NULL COMMENT 'Epoch ms del inicio de la vela',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_candles_symbol_tf_ts` (`symbol_id`, `timeframe`, `timestamp`),
  KEY `idx_candles_time` (`timestamp`),
  CONSTRAINT `fk_candles_symbol` FOREIGN KEY (`symbol_id`) 
    REFERENCES `symbols` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Historial de velas OHLCV para backtesting'
PARTITION BY RANGE (UNIX_TIMESTAMP(created_at)) (
  PARTITION p202502 VALUES LESS THAN (UNIX_TIMESTAMP('2025-03-01 00:00:00')),
  PARTITION p202503 VALUES LESS THAN (UNIX_TIMESTAMP('2025-04-01 00:00:00')),
  PARTITION p202504 VALUES LESS THAN (UNIX_TIMESTAMP('2025-05-01 00:00:00')),
  PARTITION p202505 VALUES LESS THAN (UNIX_TIMESTAMP('2025-06-01 00:00:00')),
  PARTITION p202506 VALUES LESS THAN (UNIX_TIMESTAMP('2025-07-01 00:00:00')),
  PARTITION p202507 VALUES LESS THAN (UNIX_TIMESTAMP('2025-08-01 00:00:00')),
  PARTITION p202508 VALUES LESS THAN (UNIX_TIMESTAMP('2025-09-01 00:00:00')),
  PARTITION p202509 VALUES LESS THAN (UNIX_TIMESTAMP('2025-10-01 00:00:00')),
  PARTITION p202510 VALUES LESS THAN (UNIX_TIMESTAMP('2025-11-01 00:00:00')),
  PARTITION p202511 VALUES LESS THAN (UNIX_TIMESTAMP('2025-12-01 00:00:00')),
  PARTITION p202512 VALUES LESS THAN (UNIX_TIMESTAMP('2026-01-01 00:00:00')),
  PARTITION p202601 VALUES LESS THAN (UNIX_TIMESTAMP('2026-02-01 00:00:00')),
  PARTITION p202602 VALUES LESS THAN (UNIX_TIMESTAMP('2026-03-01 00:00:00')),
  PARTITION p202603 VALUES LESS THAN (UNIX_TIMESTAMP('2026-04-01 00:00:00')),
  PARTITION pmax VALUES LESS THAN MAXVALUE
);


SET FOREIGN_KEY_CHECKS = 1;

-- ═══════════════════════════════════════════════════════════════════════════
-- QUERIES DE EJEMPLO PARA ML
-- ═══════════════════════════════════════════════════════════════════════════

-- Dataset supervisado básico:
-- SELECT 
--   tf.ema_distance, tf.rsi_value, tf.rsi_slope, tf.volatility_20,
--   tf.candle_body_ratio, tf.pattern_type, tf.distance_to_support,
--   tf.distance_to_resistance, tf.market_structure_score,
--   CASE WHEN t.status = 'PROFIT' THEN 1 ELSE 0 END AS label,
--   t.pnl_percent
-- FROM trade_features tf
-- JOIN trades t ON t.id = tf.trade_id
-- WHERE t.status IN ('PROFIT', 'LOSS')
-- ORDER BY t.opened_at;

-- Análisis de edge por patrón:
-- SELECT 
--   tf.pattern_type,
--   COUNT(*) as trades,
--   AVG(CASE WHEN t.status = 'PROFIT' THEN 1 ELSE 0 END) * 100 as win_rate,
--   AVG(t.pnl_percent) as avg_pnl
-- FROM trade_features tf
-- JOIN trades t ON t.id = tf.trade_id
-- WHERE t.status IN ('PROFIT', 'LOSS')
-- GROUP BY tf.pattern_type
-- ORDER BY win_rate DESC;
