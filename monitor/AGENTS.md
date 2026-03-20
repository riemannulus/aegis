<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# monitor

## Purpose
System monitoring and alerting. Collects runtime metrics (prices, balances, signals, positions) and sends Telegram notifications for trades, risk warnings, daily reports, and system events.

## Key Files

| File | Description |
|------|-------------|
| `metrics.py` | `MetricsCollector` — Collects and snapshots runtime metrics: candle data, signals, positions, errors. Singleton `collector` instance. Methods: `record_candle()`, `record_signal()`, `record_position()`, `snapshot()` |
| `telegram_bot.py` | `TelegramBot` — Sends notifications via Telegram Bot API. Auto-tags with [TESTNET]/[MAINNET]. Methods: `send_raw()`, `notify_system_start/stop()`, `notify_health_check()`, `send_daily_report()`, `alert_funding_rate()`, `warn_liquidation_proximity()`. No-op if token not configured. |

## For AI Agents

### Working In This Directory
- Telegram is optional — gracefully no-ops when `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` not set
- Messages auto-tagged with testnet/mainnet prefix from `settings.telegram_tag`
- Uses `requests` library for Telegram API (not python-telegram-bot async)
- `MetricsCollector` singleton: `from monitor.metrics import collector`
- Metrics snapshot is a dict used by health checks, daily reports, and WebSocket streaming

### Testing Requirements
- Mock Telegram API calls in tests — never send real messages
- Verify metric recording and snapshot retrieval

### Common Patterns
- `collector.record_candle(ts, price, balance, pnl)` — every trading cycle
- `telegram.send_raw(text)` — arbitrary notification
- `telegram.send_daily_report(date, trades, win_rate, pnl, ...)` — structured daily report

## Dependencies

### Internal
- `config/settings.py` — Telegram tokens, testnet flag

### External
- `requests` — HTTP client for Telegram Bot API

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
