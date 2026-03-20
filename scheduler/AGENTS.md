<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# scheduler

## Purpose
Main trading loop orchestrator. `TradingOrchestrator` coordinates all Aegis components using APScheduler, executing the 9-step trading cycle every 30 minutes plus periodic jobs for model retraining, funding rate checks, health monitoring, and daily reporting.

## Key Files

| File | Description |
|------|-------------|
| `orchestrator.py` | `TradingOrchestrator` — Central coordinator. Lazy-loads all components on `start()`. Manages: 30-min trading cycle (steps 1-9), weekly model retrain, 8h funding rate check, hourly health check, daily UTC report. Provides control API: `start()`, `stop()`, `emergency_stop()`, `set_leverage()`. |

## For AI Agents

### Working In This Directory
- **This is the system's main entry point** — Docker runs `TradingOrchestrator().start()`
- All components lazy-loaded in `_init_components()` to avoid import cycles
- Trading cycle steps: (1) Get candle → (2) Compute features → (3) Model predict → (4) Convert signal → (5) Risk check → (6) Execute orders → (7) Update position → (8) Stage 2 risk monitoring → (9) Record metrics
- `_run_trading_cycle_safe()` wraps the cycle to prevent scheduler death on exceptions
- Emergency stop closes all positions then shuts down the scheduler
- Control API methods (`start`, `stop`, `emergency_stop`, `set_leverage`) called by FastAPI control routes

### Testing Requirements
- `test_e2e_pipeline.py` tests the full cycle with mocked components
- Test emergency stop flow independently
- Verify scheduler jobs are registered with correct intervals

### Common Patterns
- `orch = TradingOrchestrator(); orch.start()` — system startup
- Risk engine callbacks wired in `_init_components()`: `on_emergency_close`, `on_reduce_position`, `on_telegram_alert`

## Dependencies

### Internal
- Every module in the project — orchestrator imports and coordinates all components
- `config/settings.py`, `data/`, `models/`, `strategy/`, `risk/`, `execution/`, `monitor/`

### External
- `apscheduler` — Job scheduling (BackgroundScheduler, CronTrigger, IntervalTrigger)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
