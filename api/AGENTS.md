<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# api

## Purpose
FastAPI REST API and WebSocket server for the Aegis trading system. Provides endpoints for health checks, signal/position queries, trading control, analytics, risk monitoring, model management, and real-time data streaming.

## Key Files

| File | Description |
|------|-------------|
| `main.py` | FastAPI app factory with CORS middleware, lifespan handler, and router registration. All 13 route modules + WebSocket mounted here. |
| `websocket.py` | WebSocket endpoint at `/ws/live` for real-time metrics streaming |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `routes/` | FastAPI router modules — one per resource domain (see `routes/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- All routes registered in `main.py` with prefix — add new routers there
- CORS allows all origins (`*`) — intended for local/Docker network use
- Lifespan context manager handles startup/shutdown logging
- API serves at port 8000 (Docker) or locally via `uvicorn api.main:app`

### Testing Requirements
- `test_api_endpoints.py` in tests/ — uses TestClient
- Test each route module independently

### Common Patterns
- Each route module exports a `router = APIRouter()` instance
- Routes follow REST conventions: GET for reads, POST for actions
- Route handlers import Storage/settings directly (no DI framework)

## Dependencies

### Internal
- `data/storage.py` — Data access for all query endpoints
- `config/settings.py` — Configuration access
- `scheduler/orchestrator.py` — Control endpoints interact with orchestrator

### External
- `fastapi` — Web framework
- `uvicorn` — ASGI server

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
