# Aegis — AI Crypto Futures Auto-Trading System

Aegis is an AI-driven bidirectional (long/short) auto-trading system for BTC/USDT perpetual futures on Binance USDS-M Futures. It uses a Qlib LightGBM + TRA + ADARNN ensemble to generate signals every 30 minutes, executes via CCXT, and includes a 2-stage risk management system.

> ⚠️ **All trading tests must be performed on Binance Futures Testnet only.**
> Mainnet trading is not enabled by default (`USE_TESTNET=True`).

---

## Architecture

```
Binance Vision (historical) ──► data/binance_vision.py ──► data/storage.py (SQLite)
Binance Futures WS (live)   ──► data/realtime_feed.py  ──┘
                                                           │
                                                    data/feature_engineer.py
                                                           │
                                          models/ (LightGBM + TRA + ADARNN + Ensemble)
                                                           │
                                          strategy/signal_converter.py
                                                           │
                                          risk/risk_engine.py (Stage 1 + 2)
                                                           │
                                          execution/ (BinanceExecutor / PaperTrader)
                                                           │
                               ┌───────────────────────────┴──────────────┐
                               │                                           │
                         api/main.py (FastAPI)                  monitor/telegram_bot.py
                         api/websocket.py (WS)                  monitor/metrics.py
                               │
                         backoffice/ (Streamlit)
```

---

## Installation

### Requirements
- Python 3.10+
- No GPU required (CPU-only training)

### Setup

```bash
git clone <repo>
cd aegis-trading

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your Binance API keys
```

---

## Configuration

Edit `.env`:

```env
# Testnet keys (get from https://testnet.binancefuture.com)
CT_BINANCE_TESTNET_API_KEY=your_testnet_key
CT_BINANCE_TESTNET_API_SECRET=your_testnet_secret

# Mainnet keys (Enable Futures permission, NO withdrawals)
CT_BINANCE_API_KEY=your_mainnet_key
CT_BINANCE_API_SECRET=your_mainnet_secret

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Keep True during development
USE_TESTNET=True
```

Key settings in `config/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `USE_TESTNET` | `True` | ⚠️ Always True during dev/test |
| `LEVERAGE` | `3` | Futures leverage (max 10x) |
| `MARGIN_TYPE` | `isolated` | Isolated margin only |
| `MAX_POSITION_RATIO` | `0.3` | Max 30% of capital per position |
| `MAX_DAILY_LOSS_RATIO` | `0.05` | Stop trading after 5% daily loss |
| `MAX_DRAWDOWN_RATIO` | `0.10` | Emergency stop at 10% drawdown |

---

## Running

### Download historical data

```bash
python scripts/download_binance_vision.py --symbol BTCUSDT --interval 30m --months 6
python scripts/backfill_data.py
```

### Train models

```bash
python scripts/train_models.py
```

### Run backtest (Testnet only)

```bash
python scripts/run_backtest.py --start 2024-01-01 --end 2024-06-30
```

### Docker Compose (recommended)

```bash
docker compose up -d
```

Services:
- `aegis-trader` — main trading bot
- `aegis-api` — FastAPI backend at http://localhost:8000
- `aegis-backoffice` — Streamlit dashboard at http://localhost:8501

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/signals/latest` | Latest trading signal |
| GET | `/positions` | Current Futures position |
| GET | `/decisions` | Decision audit log |
| GET | `/analytics/pnl-summary` | PnL summary |
| GET | `/analytics/funding-history` | Funding rate history |
| POST | `/control/start` | Start trading |
| POST | `/control/stop` | Stop trading |
| POST | `/control/emergency-exit` | Emergency close + stop |
| POST | `/control/set-leverage` | Update leverage |
| WS | `/ws/live` | Real-time metrics stream |

---

## Testing

```bash
# Run all tests
pytest tests/

# Specific test suites
pytest tests/test_paper_trader.py -v
pytest tests/test_risk_engine.py -v
pytest tests/test_mainnet_readiness.py -v   # mock only, no real calls

# Testnet integration tests (requires testnet API keys in .env)
pytest tests/test_binance_executor.py -v -m testnet
```

---

## Mainnet Transition Checklist

Before setting `USE_TESTNET=False`, verify **all** of the following:

- [ ] Binance account has **Futures trading enabled** (not just spot)
- [ ] API key has **Enable Futures** permission checked
- [ ] API key does **NOT** have Enable Withdrawals checked
- [ ] `CT_BINANCE_API_KEY` and `CT_BINANCE_API_SECRET` set in `.env`
- [ ] Strategy backtested over ≥ 6 months with acceptable Sharpe ratio
- [ ] All `pytest tests/` pass on Testnet
- [ ] `test_mainnet_readiness.py` passes (architecture branching verified)
- [ ] Leverage set to conservative value (1x–3x recommended for initial live)
- [ ] `MAX_POSITION_RATIO` reviewed (default 0.3 = 30% per position)
- [ ] `MAX_DAILY_LOSS_RATIO` reviewed (default 0.05 = 5% daily stop)
- [ ] `MAX_DRAWDOWN_RATIO` reviewed (default 0.10 = 10% emergency stop)
- [ ] Telegram alerts configured and tested
- [ ] Initial capital is amount you can afford to lose entirely
- [ ] Monitoring plan in place (Telegram + Streamlit dashboard)
- [ ] Emergency stop procedure known (POST /control/emergency-exit)
- [ ] Reviewed all Mainnet safety guards in `BinanceExecutor`:
  - 3x warning log on init
  - 5-second delay before first order
  - 5% max single order size
  - 10 daily trade limit
- [ ] Set `USE_TESTNET=False` only after all above are confirmed

---

## Project Structure

```
aegis-trading/
├── config/          # Settings, symbols, risk params
├── data/            # Data pipeline (Binance Vision + live feed + storage)
├── models/          # LightGBM, TRA, ADARNN, ensemble, trainer
├── strategy/        # Signal converter, position manager, decision logger
├── risk/            # 2-stage risk engine
├── execution/       # BinanceExecutor (CCXT), PaperTrader, OrderManager
├── api/             # FastAPI server + routes + WebSocket
├── backoffice/      # Streamlit admin dashboard
├── analytics/       # PnL, performance metrics, attribution
├── monitor/         # Telegram bot, metrics collector
├── scheduler/       # APScheduler orchestrator (main loop)
├── scripts/         # CLI scripts (download, train, backtest)
└── tests/           # pytest test suite
```

---

## License

MIT
