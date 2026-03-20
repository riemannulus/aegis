<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# pages

## Purpose
Streamlit page modules for the Aegis backoffice dashboard. Each file is a self-contained page auto-discovered by Streamlit's multi-page app system. Numbered prefixes control sidebar ordering.

## Key Files

| File | Description |
|------|-------------|
| `01_live_dashboard.py` | Real-time system status: current position, equity curve, latest signals, system health |
| `02_decision_log.py` | Decision audit trail — every trade decision with reasoning, filterable |
| `03_trade_journal.py` | Individual trade analysis with candle charts and entry/exit markers |
| `04_pnl_analytics.py` | PnL summary, cumulative returns, Sharpe ratio, win rate analytics |
| `05_model_monitor.py` | Model performance monitoring: IC, prediction distribution, feature importance |
| `06_risk_dashboard.py` | Risk metrics: drawdown, position limits usage, liquidation proximity |
| `07_backtest_viewer.py` | Backtest results viewer: equity curves, trade stats, comparison |
| `08_system_ops.py` | System operations: start/stop trading, set leverage, emergency exit |

## For AI Agents

### Working In This Directory
- Each page imports from `backoffice.api_client` for data
- Pages use `st.plotly_chart()` for visualization, `st.metric()` for KPIs
- Numeric prefix determines sidebar order — maintain the convention
- Adding a new page: create `09_name.py` and it auto-appears in sidebar

### Common Patterns
- `import streamlit as st` + `from backoffice.api_client import ...`
- Data fetch → transform → display pattern in each page
- Error handling via `api_client` graceful fallbacks (returns None on failure)

## Dependencies

### Internal
- `backoffice/api_client.py` — All data access

### External
- `streamlit`, `plotly` — UI framework

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
