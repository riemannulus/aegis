<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# risk

## Purpose
2-stage risk management engine for Futures trading. Stage 1 (pre-order): validates position limits and daily loss before order placement. Stage 2 (real-time): monitors open positions for stop-loss, take-profit, trailing stop, drawdown, liquidation proximity, and adverse funding rates.

## Key Files

| File | Description |
|------|-------------|
| `risk_engine.py` | `RiskEngine` — Main 2-stage engine. `check_pre_order()` (Stage 1) and `monitor_position()` (Stage 2). Fires callbacks: `on_emergency_close`, `on_reduce_position`, `on_telegram_alert` |
| `position_limits.py` | `PositionLimits` — Enforces max position ratio (30%), max daily loss (5%), max order count. Returns `LimitCheckResult` |
| `drawdown_monitor.py` | `DrawdownMonitor` — Tracks peak equity and current drawdown. Triggers `DrawdownAction` (NONE/REDUCE/EMERGENCY_STOP) at configurable thresholds (default 10%) |

## For AI Agents

### Working In This Directory
- **Stage 1** (`check_pre_order`): Called before every order. Checks position limits, daily loss, account balance. Returns `Stage1Result` with `passed` bool and `reason`.
- **Stage 2** (`monitor_position`): Called every candle while position is open. Checks: stop-loss, take-profit, trailing stop (activates at +2%, trails at 1%), drawdown, liquidation proximity (80% warn → reduce 50%, 90% → emergency close), funding rate alerts (>0.1%).
- Emergency close callback wired to `TradingOrchestrator.emergency_stop()`
- Regime-aware: volatile regime tightens limits via `RegimeParams`

### Testing Requirements
- `test_risk_engine.py` in tests/ — test both stages independently
- Test liquidation proximity edge cases carefully
- Test drawdown cascading: REDUCE → EMERGENCY_STOP

### Common Patterns
- `risk_result = engine.check_pre_order(order_usdt, balance, current_pos)` — Stage 1
- `stage2 = engine.monitor_position(entry, current, side, size, leverage, equity, liq, funding)` — Stage 2
- `engine.tick_candle()` — must be called every cycle to update internal state

## Dependencies

### Internal
- `config/settings.py` — Risk parameter defaults
- `strategy/regime_detector.py` — Regime-aware parameter adjustment

### External
- None (pure Python logic)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
