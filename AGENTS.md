<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# Aegis — AI Crypto Futures Auto-Trading System

## Purpose
AI-driven bidirectional (long/short) auto-trading system for BTC/USDT perpetual futures on Binance USDS-M Futures. Uses a Qlib LightGBM + TRA + ADARNN ensemble to generate signals every 30 minutes, executes via CCXT, with 2-stage risk management.

## Key Files

| File | Description |
|------|-------------|
| `pyproject.toml` | Python project config (hatchling build, dependencies) |
| `docker-compose.yml` | 3-service Docker orchestration (trader, api, backoffice) |
| `Dockerfile` | Container image definition |
| `.env` | Environment variables (API keys, testnet toggle) — **never commit** |
| `README.md` | Project documentation and mainnet checklist |
| `SPEC_PROMPT.md` | Original system specification |
| `uv.lock` | Dependency lock file (uv package manager) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `config/` | Application settings, risk params, symbol config (see `config/AGENTS.md`) |
| `data/` | Data pipeline: collection, storage (SQLite), feature engineering (see `data/AGENTS.md`) |
| `models/` | ML models: LightGBM, TRA, ADARNN, ensemble, trainer (see `models/AGENTS.md`) |
| `strategy/` | Signal conversion, position management, decision logging (see `strategy/AGENTS.md`) |
| `risk/` | 2-stage risk engine, position limits, drawdown monitoring (see `risk/AGENTS.md`) |
| `execution/` | Order execution: Binance (CCXT), paper trading, order manager (see `execution/AGENTS.md`) |
| `api/` | FastAPI REST + WebSocket server (see `api/AGENTS.md`) |
| `backoffice/` | Streamlit admin dashboard with 8 pages (see `backoffice/AGENTS.md`) |
| `analytics/` | PnL calculation, performance metrics, attribution (see `analytics/AGENTS.md`) |
| `monitor/` | Telegram alerts and metrics collection (see `monitor/AGENTS.md`) |
| `scheduler/` | APScheduler orchestrator — main trading loop (see `scheduler/AGENTS.md`) |
| `scripts/` | CLI scripts for data download, training, backtesting (see `scripts/AGENTS.md`) |
| `tests/` | pytest test suite (see `tests/AGENTS.md`) |

## For AI Agents

### Architecture Flow
```
Data (Binance) → Features → ML Ensemble → Signal → Risk Check → Execution → Monitoring
```
The `scheduler/orchestrator.py` ties all layers together in a 30-min trading cycle (steps 1-9).

### Working In This Directory
- **Testnet only**: `USE_TESTNET=True` is enforced in dev. Never set to `False` without completing the mainnet checklist in README.
- **Docker Compose**: 3 services on `aegis-net` bridge network. API at `:8000`, backoffice at `:8501`.
- **Package manager**: Uses `uv` (see `uv.lock`). Build backend is `hatchling`.
- **Python 3.10+** required. No GPU needed.

### Testing Requirements
- Run `pytest tests/` before committing
- `asyncio_mode = "auto"` configured in pyproject.toml
- Testnet integration tests require API keys in `.env`

### Key Dependencies
- `ccxt>=4.0` — Exchange integration (v4 API, not v3)
- `lightgbm`, `torch`, `scikit-learn` — ML models
- `fastapi`, `uvicorn` — API server
- `streamlit`, `plotly` — Dashboard UI
- `apscheduler` — Task scheduling
- `python-telegram-bot` — Alerts
- `sqlalchemy` — Database ORM
- `pydantic-settings` — Configuration management

### Safety Critical
- All order execution goes through `risk/risk_engine.py` (2-stage check)
- Emergency stop: `POST /control/emergency-exit` or `orchestrator.emergency_stop()`
- Mainnet has additional safety guards: 3x warning, 5s delay, 5% max order, 10 daily trades

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
