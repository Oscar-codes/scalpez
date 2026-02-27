# QuantPulse – Infrastructure PRD

## 1. Purpose

Define the technical infrastructure required to support the QuantPulse real-time prediction and paper trading system.

This document focuses exclusively on backend infrastructure, real-time streaming, persistence layer, scalability model, and deployment readiness.

---

# 2. Infrastructure Objectives

The infrastructure must:

- Support real-time WebSocket streaming from Deriv.
- Process high-frequency tick data asynchronously.
- Build and manage candle data efficiently.
- Execute signal and simulation engines with low latency.
- Persist critical trading events.
- Provide internal WebSocket broadcasting to frontend.
- Be scalable from local development to VPS/cloud.

---

# 3. High-Level Architecture

```
Deriv WebSocket
        ↓
Deriv Client (Async Layer)
        ↓
Candle Builder Service
        ↓
Indicator & Signal Engine
        ↓
Trade Simulation Engine
        ↓
Persistence Layer (SQLite → PostgreSQL)
        ↓
Internal WebSocket Broadcast (FastAPI)
        ↓
Frontend Dashboard
```

---

# 4. Backend Infrastructure Components

## 4.1 API Layer

Technology: FastAPI

Responsibilities:
- Application entry point
- WebSocket endpoint for frontend
- Health check endpoint
- Startup & shutdown lifecycle management
- Dependency injection configuration

Requirements:
- Async support
- CORS enabled
- Production-ready configuration

---

## 4.2 WebSocket Streaming Layer

Technology: websockets (async)

Responsibilities:
- Connect to Deriv WebSocket endpoint
- Subscribe to selected synthetic indices
- Handle reconnection with exponential backoff
- Emit ticks to internal processing layer
- Ensure no business logic inside this layer

Performance Requirement:
- Sustain high tick throughput without blocking event loop

---

## 4.3 Data Processing Layer

### Candle Builder

Responsibilities:
- Convert tick stream into 1-minute candles
- Store only closed candles
- Prevent repainting
- Maintain memory-efficient rolling buffer

### Indicator Engine

Responsibilities:
- Compute EMA (configurable periods)
- Compute RSI
- Operate only on closed candles
- Stateless design

### Signal Engine

Responsibilities:
- Apply multi-confirmation logic
- Validate risk-reward structure
- Produce structured signal objects

### Trade Simulation Engine

Responsibilities:
- Open simulated trades on valid signals
- Monitor TP / SL / Expiration
- Calculate movement percentage
- Close trades deterministically

---

## 4.4 Persistence Layer

Initial Technology: SQLite
Future Migration: PostgreSQL

Responsibilities:
- Persist signals
- Persist simulated trades
- Support statistical analysis queries
- Isolate database access through repository pattern

Design Rules:
- Domain models must not depend on ORM models
- Repository layer handles mapping

---

## 4.5 Database Schema

### signals
- id
- asset
- timestamp
- type
- confidence
- entry_price
- stop_loss
- take_profit
- rr_ratio

### trades
- id
- signal_id
- asset
- entry_price
- stop_loss
- take_profit
- open_time
- close_time
- result
- duration_seconds
- movement_percentage

Indexes:
- asset
- timestamp
- result

---

# 5. Scalability Strategy

## Phase 1 – Local Development
- SQLite
- Single process
- In-memory candle buffer

## Phase 2 – VPS Deployment
- PostgreSQL
- Dockerized backend
- Nginx reverse proxy

## Phase 3 – Horizontal Scaling
- Redis for pub/sub
- Separate streaming worker
- Dedicated simulation worker

---

# 6. Performance Requirements

- Tick processing latency < 200ms
- Signal generation latency < 300ms
- WebSocket broadcast latency < 500ms
- Memory growth controlled via rolling buffers

---

# 7. Security Considerations

- Environment variables for configuration
- No API keys hardcoded
- Input validation on WebSocket layer
- Rate limiting (future phase)

---

# 8. Observability & Logging

- Structured logging (JSON format)
- Error tracking
- Signal generation logs
- Trade lifecycle logs

Future:
- Prometheus metrics
- Grafana dashboard

---

# 9. Deployment Readiness

Infrastructure must support:

- Dockerfile
- docker-compose configuration
- .env configuration management
- Separation of development and production settings

---

# 10. Definition of Done (Infrastructure)

Infrastructure is considered production-ready when:

- Deriv connection auto-recovers on disconnect
- Candle generation is stable
- Signals persist correctly
- Trades close deterministically
- WebSocket frontend updates in real time
- System runs continuously without memory leak

---

End of Infrastructure PRD