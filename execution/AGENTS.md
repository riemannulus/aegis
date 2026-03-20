<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# execution

## Purpose
Order execution layer for Binance Futures. Provides exchange integration via CCXT, paper trading simulator, and order management with retry logic. Handles testnet/mainnet switching with safety guards for mainnet.

## Key Files

| File | Description |
|------|-------------|
| `base.py` | `BaseExecutor` ABC — interface for all executors: `submit_order()`, `get_position()`, `get_balance()`, `close_position()`, `initialize_futures()`, `get_funding_rate()` |
| `binance_executor.py` | `BinanceExecutor` — CCXT-based Binance Futures executor. Testnet via sandbox mode. Mainnet safety: 3x warning log, 5s first-order delay, 5% max single order ratio, 10 daily trade limit. Network retries with exponential backoff (1/2/4s). |
| `paper_trader.py` | `PaperTrader` — Simulated executor for backtesting and paper trading. Tracks virtual balance and positions. |
| `order_manager.py` | `OrderManager` — Higher-level order submission with slippage checks, order tracking, and Storage persistence |

## For AI Agents

### Working In This Directory
- **CCXT v4 API** is used — method signatures differ from v3 documentation
- `BinanceExecutor` auto-switches testnet/mainnet via `settings.USE_TESTNET`
- Mainnet safety guards are hardcoded constants (not configurable) — intentional
- `_retry_on_network_error` wraps all exchange calls with 3 retries and exponential backoff
- `PaperTrader` implements the same `BaseExecutor` interface for drop-in replacement
- Orders are market orders only (no limit orders implemented)

### Testing Requirements
- `test_binance_executor.py` and `test_paper_trader.py` in tests/
- Mock CCXT exchange for unit tests — never hit real API in CI
- Testnet integration tests require `CT_BINANCE_TESTNET_API_KEY` in `.env`

### Common Patterns
- `executor.initialize_futures(symbol, leverage, margin_type)` — must be called before trading
- `executor.get_position(symbol)` → dict with `side`, `size`, `entry_price`, `liquidation_price`, `unrealized_pnl`
- `executor.get_balance()` → dict with `total`, `available`, `used`
- `order_manager.submit_market_order(symbol, side, amount, intended_price)` — primary order entry

## Dependencies

### Internal
- `config/settings.py` — API keys, exchange configuration
- `data/storage.py` — Order/trade persistence (via OrderManager)

### External
- `ccxt>=4.0` — Exchange API client (Binance Futures)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
