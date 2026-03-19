"""HTTP client for the Aegis FastAPI backend.

All dashboard pages import this module to fetch data.
Falls back gracefully if the API is unavailable (shows empty/demo data).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"
TIMEOUT = 5  # seconds


def _get(path: str, params: Optional[dict] = None) -> Any:
    """GET request with timeout and graceful error handling."""
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        logger.warning("API not reachable at %s%s", API_BASE, path)
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning("API HTTP error %s: %s", path, e)
        return None
    except Exception as e:
        logger.warning("API error %s: %s", path, e)
        return None


def _post(path: str, json: Optional[dict] = None) -> Any:
    try:
        resp = requests.post(f"{API_BASE}{path}", json=json or {}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("API POST error %s: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def get_health() -> Optional[dict]:
    return _get("/health")


def get_latest_signals(limit: int = 20) -> Optional[list]:
    return _get("/signals/latest", params={"limit": limit})


def get_positions() -> Optional[dict]:
    return _get("/positions")


def get_metrics() -> Optional[dict]:
    return _get("/metrics")


def get_funding_history(limit: int = 50) -> Optional[list]:
    return _get("/funding-history", params={"limit": limit})


def get_decisions(limit: int = 200, decision_type: Optional[str] = None) -> Optional[list]:
    params: dict = {"limit": limit}
    if decision_type:
        params["type"] = decision_type
    return _get("/decisions", params=params)


def get_trades(limit: int = 500) -> Optional[list]:
    return _get("/trades", params={"limit": limit})


def get_equity_curve() -> Optional[list]:
    return _get("/analytics/equity-curve")


def get_performance_summary() -> Optional[dict]:
    return _get("/analytics/performance")


def get_attribution() -> Optional[dict]:
    return _get("/analytics/attribution")


def get_model_metrics() -> Optional[dict]:
    return _get("/models/metrics")


def get_risk_status() -> Optional[dict]:
    return _get("/risk/status")


def get_risk_events(limit: int = 100) -> Optional[list]:
    return _get("/risk/events", params={"limit": limit})


def get_backtest_list() -> Optional[list]:
    return _get("/backtests")


def get_backtest_detail(backtest_id: str) -> Optional[dict]:
    return _get(f"/backtests/{backtest_id}")


def get_system_logs(level: str = "INFO", limit: int = 200) -> Optional[list]:
    return _get("/system/logs", params={"level": level, "limit": limit})


def get_scheduler_status() -> Optional[dict]:
    return _get("/system/scheduler")


def get_pipeline_latency() -> Optional[dict]:
    return _get("/system/latency")


def post_control_start() -> Optional[dict]:
    return _post("/control/start")


def post_control_stop() -> Optional[dict]:
    return _post("/control/stop")


def post_emergency_exit() -> Optional[dict]:
    return _post("/control/emergency-exit")


def post_set_leverage(leverage: int) -> Optional[dict]:
    return _post("/control/set-leverage", json={"leverage": leverage})


def post_force_retrain() -> Optional[dict]:
    return _post("/control/force-retrain")
