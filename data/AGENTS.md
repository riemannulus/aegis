<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# data

## Purpose
Data pipeline layer: historical data download (Binance Vision), real-time WebSocket feed, SQLite storage (SQLAlchemy ORM), and feature engineering for ML models. All market data flows through this layer before reaching the model.

## Key Files

| File | Description |
|------|-------------|
| `storage.py` | SQLAlchemy ORM with SQLite backend. Defines tables: `Candle`, `FundingRate`, `Trade`, `Decision`, `Signal`, `DailyMetrics`. Provides `Storage` class with query methods (get_recent_candles, save_trade, etc.) |
| `collector.py` | `RealtimeCollector` — live OHLCV candles, funding rates, and open interest from Binance Futures via CCXT |
| `feature_engineer.py` | `compute_features()` — 20+ features from OHLCV data (momentum, volatility, volume, funding). Qlib Alpha158-compatible format for 30m/1h timeframes |
| `realtime_feed.py` | WebSocket-based real-time data stream handler with candle-close callbacks |
| `binance_vision.py` | Binance Vision historical data downloader (CSV bulk data) |
| `aegis.db` | SQLite database file (not committed) |

## For AI Agents

### Working In This Directory
- `Storage` class is the single database access point — all modules use it for reads/writes
- DB path configurable via `AEGIS_DB_PATH` env var (default: `data/aegis.db`)
- SQLAlchemy ORM with `DeclarativeBase` — add new tables by subclassing `Base`
- Feature engineering uses pandas DataFrames throughout — inputs are OHLCV + funding rates
- `compute_features()` returns NaN-handled DataFrame (forward-fill then dropna)
- CCXT v4 API is used (not v3) — method signatures differ from older docs

### Testing Requirements
- `test_data_collector.py` and `test_feature_engineer.py` in tests/
- Use in-memory SQLite for storage tests (`:memory:`)
- Feature tests need at least 50 candle rows for valid computation

### Common Patterns
- `storage.get_recent_candles(limit=N)` returns pandas DataFrame
- `compute_features(candles_df, funding_df)` is the main feature entry point
- Timestamps are millisecond epoch integers in the DB

## Dependencies

### Internal
- `config/settings.py` — Exchange configuration for collector

### External
- `sqlalchemy` — ORM and database access
- `pandas`, `numpy` — Data manipulation
- `ccxt>=4.0` — Exchange API (v4)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
