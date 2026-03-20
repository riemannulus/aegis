<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# analytics

## Purpose
Trade analytics and performance reporting. Calculates per-trade PnL with leverage and funding costs, computes performance metrics (Sharpe, win rate, max drawdown), performs attribution analysis, and generates summary reports.

## Key Files

| File | Description |
|------|-------------|
| `pnl_calculator.py` | `PnLCalculator` — Per-trade PnL with leverage, funding costs, trading fees. Produces equity curves and BTC Buy&Hold benchmark comparison. Uses `TradePnL` dataclass. |
| `performance_metrics.py` | Performance metric computation: Sharpe ratio, Sortino, win rate, profit factor, max drawdown |
| `attribution.py` | Trade attribution analysis — breaks down PnL by signal type, time period, market regime |
| `report_generator.py` | Report generation for daily/weekly summaries |

## For AI Agents

### Working In This Directory
- `TradePnL` dataclass: `trade_id`, `entry/exit_time`, `direction` (+1/-1), `entry/exit_price`, `size`, `leverage`, plus computed fields
- Equity curves compare strategy vs BTC Buy&Hold baseline
- All calculations account for leverage and funding costs (Futures-specific)
- Uses pandas DataFrames for time-series operations

### Testing Requirements
- `test_analytics.py` in tests/
- Test with known trade sequences to verify PnL math
- Verify leverage multiplier is applied correctly

### Common Patterns
- `calculator.compute_trade_pnl(trade)` → `TradePnL`
- `metrics.compute(trades_df)` → dict of performance metrics

## Dependencies

### Internal
- `data/storage.py` — Trade data retrieval

### External
- `pandas`, `numpy` — Data processing and calculations

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
