# QuantPulse

Real-time scalping signal engine using Deriv WebSocket API.

## Features

- Real-time tick streaming
- EMA 9 / EMA 21
- RSI 14
- Smart signal generation
- Paper trading simulation
- Historical signal tracking
- Scalping focused (15–30 min trades)
- RR 1:1 to 1:3

## Architecture

- FastAPI backend
- WebSocket integration with Deriv
- Clean Architecture (Domain, Application, Infrastructure)
- Async processing
- Ready for horizontal scaling

## Run backend

```bash
cd backend
uvicorn main:app --reload