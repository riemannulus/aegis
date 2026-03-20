<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# routes

## Purpose
FastAPI router modules organized by domain. Each file defines an `APIRouter` with related endpoints for one area of the trading system.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package init — re-exports all routers |
| `health.py` | `GET /health` — system health check, component status |
| `signals.py` | `GET /signals/latest` — latest trading signal |
| `positions.py` | `GET /positions` — current Futures position |
| `decisions.py` | `GET /decisions` — decision audit log |
| `analytics.py` | `GET /analytics/pnl-summary`, `/analytics/equity-curve` — PnL analytics |
| `control.py` | `POST /control/start`, `/stop`, `/emergency-exit`, `/set-leverage` — trading control |
| `trades.py` | Trade history endpoints |
| `funding.py` | `GET /funding-history` — funding rate history |
| `metrics.py` | `GET /metrics` — system metrics snapshot |
| `risk.py` | `GET /risk` — risk status and limits |
| `models.py` | `GET /models` — model info and performance |
| `backtests.py` | Backtest management endpoints |
| `system.py` | `GET /system` — system status and configuration |

## For AI Agents

### Working In This Directory
- Each file follows the same pattern: `router = APIRouter()` with `@router.get/post` decorators
- Adding a new route file: create the file, add router, then register in `api/main.py`
- Routes import from `data.storage`, `config.settings`, etc. directly
- Error handling: return appropriate HTTP status codes, not exceptions

### Common Patterns
- `router = APIRouter()` at module level
- `from data.storage import Storage` for data access
- Response models are inline dicts (no separate Pydantic response schemas)

## Dependencies

### Internal
- `data/storage.py` — Query data
- `config/settings.py` — Configuration
- `analytics/` — PnL computation for analytics routes
- `risk/risk_engine.py` — Risk status for risk routes

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
