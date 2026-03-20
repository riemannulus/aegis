<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# scripts

## Purpose
CLI utility scripts for data management, model training, and backtesting. Intended to be run directly via `python scripts/<name>.py` with command-line arguments.

## Key Files

| File | Description |
|------|-------------|
| `download_binance_vision.py` | Downloads historical OHLCV data from Binance Vision (bulk CSV). Args: `--symbol`, `--interval`, `--months` |
| `backfill_data.py` | Backfills gaps in stored candle data from exchange API |
| `train_models.py` | Trains all ML models (LightGBM, TRA, ADARNN, ensemble). Saves to `models/saved/` |
| `run_backtest.py` | Runs strategy backtest over historical data. Args: `--start`, `--end` |
| `fetch_ccxt_candles.py` | Fetches candle data via CCXT REST API (alternative to Binance Vision) |
| `paper_trade_sim.py` | Paper trading simulation script |

## For AI Agents

### Working In This Directory
- Scripts are standalone CLI tools — not imported by other modules
- Use `argparse` for command-line arguments
- Scripts import from the main codebase (`data.storage`, `models.trainer`, etc.)
- Data download scripts should be run before training or backtesting

### Testing Requirements
- Scripts tested indirectly via integration tests
- Manual verification recommended for data download scripts

### Common Patterns
- `python scripts/download_binance_vision.py --symbol BTCUSDT --interval 30m --months 6`
- `python scripts/train_models.py`
- `python scripts/run_backtest.py --start 2024-01-01 --end 2024-06-30`

## Dependencies

### Internal
- `data/`, `models/`, `execution/`, `analytics/` — Scripts orchestrate these modules

### External
- `tqdm` — Progress bars
- `argparse` — CLI argument parsing (stdlib)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
