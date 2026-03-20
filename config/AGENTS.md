<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# config

## Purpose
Centralized configuration for the Aegis trading system. Uses Pydantic Settings to load from `.env` file with type validation. Contains trading parameters, risk limits, and symbol definitions.

## Key Files

| File | Description |
|------|-------------|
| `settings.py` | Main `Settings` class (pydantic-settings): API keys, trading params, risk limits, testnet/mainnet branching. Singleton `settings` instance used everywhere. Also provides `build_ccxt_exchange()` factory. |
| `risk_params.py` | Risk parameter constants and configuration |
| `symbols.py` | Trading symbol definitions (default: `BTC/USDT:USDT`) |

## For AI Agents

### Working In This Directory
- `Settings` uses `pydantic-settings` `BaseSettings` with `.env` file loading
- The `settings` singleton at module level is imported throughout the codebase — changing its structure affects every module
- `USE_TESTNET` flag controls testnet/mainnet branching via `@model_validator`
- Never hardcode API keys — they come from `.env` environment variables
- `MARKET_TYPE` must stay `"future"` — changing to `"spot"` breaks the entire system

### Testing Requirements
- Test with `USE_TESTNET=True` always
- Mock `settings` when unit testing other modules

### Common Patterns
- `from config.settings import settings` — universal import pattern
- Settings fields use `CT_` prefix for Binance credentials

## Dependencies

### External
- `pydantic-settings` — Settings management with env file support
- `ccxt` — Used in `build_ccxt_exchange()` factory method

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
