<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# backoffice

## Purpose
Streamlit multi-page admin dashboard for monitoring and controlling the Aegis trading system. Communicates with the FastAPI backend via HTTP client. Provides 8 pages covering live monitoring, trade analysis, risk management, and system operations.

## Key Files

| File | Description |
|------|-------------|
| `app.py` | Streamlit entry point — page config, sidebar navigation |
| `api_client.py` | HTTP client for FastAPI backend. `API_BASE` from `AEGIS_API_URL` env var (default `http://localhost:8000`). Graceful fallback when API unavailable. |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `pages/` | Streamlit page modules (numbered for sidebar ordering) (see `pages/AGENTS.md`) |
| `components/` | Reusable UI components (see `components/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Streamlit multi-page app: pages in `pages/` dir auto-discovered by Streamlit
- Page files named with numeric prefix for sidebar ordering: `01_`, `02_`, etc.
- All data fetched via `api_client.py` — never import backend modules directly
- `AEGIS_API_URL` env var configures API base (Docker: `http://aegis-api:8000`)
- Graceful degradation: shows empty/demo data when API is unreachable

### Testing Requirements
- `test_backoffice_e2e.py` — Playwright-based E2E tests
- Screenshots saved to `tests/screenshots/`
- Test with mock API responses for unit-level tests

### Common Patterns
- `from backoffice.api_client import get_health, get_positions, ...` — data access
- `st.plotly_chart()` for interactive charts (Plotly)
- `st.metric()` for KPI cards

## Dependencies

### Internal
- `api/` — All data comes through the REST API

### External
- `streamlit` — Dashboard framework
- `plotly` — Interactive charts
- `requests` — HTTP client (in api_client.py)

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
