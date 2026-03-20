"""Comprehensive E2E tests for all Aegis API endpoints."""

from __future__ import annotations

import os
import tempfile
import time
from typing import Generator

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: patch Storage to use an isolated temp DB for all tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory) -> str:
    db_file = tmp_path_factory.mktemp("aegis_test") / "test.db"
    return str(db_file)


@pytest.fixture(scope="session", autouse=True)
def patch_storage(test_db_path: str):
    """Replace data.storage.Storage with a version that uses the test DB by default.

    Only overrides the default db_path — if a caller explicitly passes a
    different db_path (e.g. test_data_collector's tmp_storage fixture),
    that explicit path is respected.
    """
    import data.storage as storage_mod

    _OrigStorage = storage_mod.Storage
    _default_db = storage_mod.DB_PATH

    class _TestStorage(_OrigStorage):
        def __init__(self, db_path: str = test_db_path):  # noqa: B006
            if db_path == _default_db:
                db_path = test_db_path
            super().__init__(db_path=db_path)

    storage_mod.Storage = _TestStorage
    yield test_db_path
    storage_mod.Storage = _OrigStorage


@pytest.fixture(scope="session")
def client(patch_storage) -> TestClient:
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Fixture: seed the DB with realistic sample data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seeded_db(patch_storage: str):
    """Insert sample rows into all tables so endpoint tests can verify data."""
    import data.storage as storage_mod

    storage = storage_mod.Storage(db_path=patch_storage)
    now_ms = int(time.time() * 1000)
    base_price = 65_000.0

    # 10 candles with BTC-like prices
    candles = []
    for i in range(10):
        ts = now_ms - (10 - i) * 1_800_000  # 30-min intervals
        candles.append({
            "timestamp": ts,
            "symbol": "BTCUSDT",
            "interval": "30m",
            "open": base_price + i * 50,
            "high": base_price + i * 50 + 100,
            "low": base_price + i * 50 - 100,
            "close": base_price + i * 50 + 30,
            "volume": 500.0 + i * 10,
            "quote_volume": (500.0 + i * 10) * (base_price + i * 50),
            "count": 1000 + i,
            "taker_buy_volume": 250.0,
            "taker_buy_quote_volume": 250.0 * base_price,
        })
    storage.upsert_candles(candles)

    # 5 trades with mixed PnL (3 wins, 2 losses)
    trade_pnls = [120.0, -45.0, 200.0, -30.0, 80.0]
    for i, pnl in enumerate(trade_pnls):
        ts = now_ms - (5 - i) * 3_600_000
        storage.insert_trade({
            "timestamp": ts,
            "side": "long" if pnl > 0 else "short",
            "entry_price": base_price,
            "exit_price": base_price + pnl / 0.01,
            "pnl": pnl,
            "funding_cost": 0.5,
        })

    # 5 decisions
    decisions = [
        ("EXECUTE", "long", 1.5, "trending", "Strong momentum"),
        ("SKIP", None, 0.3, "ranging", "Signal too weak"),
        ("EXECUTE", "short", -1.2, "volatile", "Reversal signal"),
        ("REJECTED", None, 0.1, "ranging", "Risk limit hit"),
        ("EXECUTE", "long", 0.9, "trending", "Breakout confirmed"),
    ]
    for i, (decision, direction, z_score, regime, reason) in enumerate(decisions):
        ts = now_ms - (5 - i) * 7_200_000
        storage.insert_decision({
            "timestamp": ts,
            "decision": decision,
            "direction": direction,
            "z_score": z_score,
            "regime": regime,
            "reason": reason,
        })

    # 2 positions
    for i in range(2):
        ts = now_ms - (2 - i) * 3_600_000
        storage.insert_position({
            "timestamp": ts,
            "side": "long",
            "entry_price": base_price + i * 100,
            "size": 0.1 + i * 0.05,
            "unrealized_pnl": 50.0 + i * 20,
            "liquidation_price": base_price - 5_000,
        })

    # 3 signals
    for i in range(3):
        ts = now_ms - (3 - i) * 1_800_000
        storage.insert_signal({
            "timestamp": ts,
            "model_name": f"model_{i}",
            "prediction": 0.6 + i * 0.05,
            "position_signal": 0.4 + i * 0.1,
        })

    # 3 funding rates
    for i in range(3):
        ts = now_ms - (3 - i) * 28_800_000  # 8h intervals
        storage.upsert_funding_rate({
            "timestamp": ts,
            "symbol": "BTCUSDT",
            "funding_rate": 0.0001 + i * 0.00005,
            "mark_price": base_price + i * 10,
        })

    return storage


# ===========================================================================
# Tests: Empty DB (client without seeded_db)
# ===========================================================================

class TestEmptyDB:
    """All endpoints must return 200 even with an empty database."""

    def test_health(self, client):
        r = client.get("/health/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running"
        assert "testnet" in data
        assert "version" in data
        assert "environment" in data
        assert "models_loaded" in data
        assert "uptime" in data
        assert "db_size_mb" in data

    def test_positions_root(self, client):
        r = client.get("/positions/")
        assert r.status_code == 200
        data = r.json()
        assert data["side"] == "flat"
        assert data["size"] == 0.0

    def test_positions_current(self, client):
        r = client.get("/positions/current")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_metrics(self, client):
        r = client.get("/metrics/")
        assert r.status_code == 200
        data = r.json()
        assert "today_realized_pnl" in data
        assert "today_funding_cost" in data
        assert "unrealized_pnl" in data
        assert "total_trades_today" in data
        assert "account_balance" in data

    def test_trades_empty(self, client):
        r = client.get("/trades/?limit=10")
        assert r.status_code == 200
        assert r.json() == []

    def test_funding_history_empty(self, client):
        r = client.get("/funding-history/?limit=1")
        assert r.status_code == 200
        assert r.json() == []

    def test_signals_latest_empty(self, client):
        r = client.get("/signals/latest")
        assert r.status_code == 200
        assert r.json() == []

    def test_decisions_empty(self, client):
        r = client.get("/decisions/")
        assert r.status_code == 200
        assert r.json() == []

    def test_analytics_pnl_summary_empty(self, client):
        r = client.get("/analytics/pnl-summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_trades"] == 0
        assert data["win_rate"] == 0.0
        assert data["total_pnl"] == 0.0

    def test_analytics_equity_curve_empty(self, client):
        r = client.get("/analytics/equity-curve")
        assert r.status_code == 200
        assert r.json() == []

    def test_analytics_performance_empty(self, client):
        r = client.get("/analytics/performance")
        assert r.status_code == 200
        data = r.json()
        assert data["total_trades"] == 0

    def test_analytics_attribution(self, client):
        r = client.get("/analytics/attribution")
        assert r.status_code == 200
        data = r.json()
        assert "by_model" in data
        assert "by_regime" in data
        assert "by_hour" in data

    def test_models_metrics(self, client):
        r = client.get("/models/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "last_retrain_at" in data
        assert "model_files" in data
        assert isinstance(data["model_files"], list)

    def test_risk_status_empty(self, client):
        r = client.get("/risk/status")
        assert r.status_code == 200
        data = r.json()
        assert data["current_drawdown_pct"] == 0.0
        assert data["risk_level"] == "low"
        assert "daily_loss_used_pct" in data
        assert "daily_trades" in data
        assert "high_water_mark" in data
        assert "current_equity" in data

    def test_risk_events(self, client):
        r = client.get("/risk/events")
        assert r.status_code == 200
        assert r.json() == []

    def test_backtests(self, client):
        r = client.get("/backtests/")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_system_logs(self, client):
        r = client.get("/system/logs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_system_scheduler(self, client):
        r = client.get("/system/scheduler")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data
        assert "jobs" in data

    def test_system_latency(self, client):
        r = client.get("/system/latency")
        assert r.status_code == 200
        data = r.json()
        assert "measured_at" in data

    def test_control_status(self, client):
        r = client.get("/control/status")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data
        assert "testnet" in data
        assert "symbol" in data
        assert "timeframe" in data

    def test_control_start(self, client):
        # Reset to stopped state first
        client.post("/control/stop")
        r = client.post("/control/start")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "started" in data["message"].lower()

    def test_control_stop(self, client):
        # Ensure running first
        client.post("/control/start")
        r = client.post("/control/stop")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "stopped" in data["message"].lower()

    def test_control_emergency_exit(self, client):
        r = client.post("/control/emergency-exit")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "emergency" in data["message"].lower() or "exit" in data["message"].lower()

    def test_control_set_leverage(self, client):
        r = client.post("/control/set-leverage", json={"leverage": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "3" in data["message"]

    def test_control_set_leverage_invalid(self, client):
        r = client.post("/control/set-leverage", json={"leverage": 200})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False

    def test_control_force_retrain(self, client):
        r = client.post("/control/force-retrain")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True


# ===========================================================================
# Tests: Seeded DB — verify data is returned correctly
# ===========================================================================

class TestSeededDB:
    """Verify endpoints return non-empty data with correct field names after seeding."""

    def test_trades_with_data(self, client, seeded_db):
        r = client.get("/trades/?limit=10")
        assert r.status_code == 200
        trades = r.json()
        assert len(trades) > 0
        trade = trades[0]
        assert "timestamp" in trade
        assert "side" in trade
        assert "entry_price" in trade
        assert "exit_price" in trade
        assert "pnl" in trade

    def test_funding_history_with_data(self, client, seeded_db):
        r = client.get("/funding-history/?limit=1")
        assert r.status_code == 200
        rates = r.json()
        assert len(rates) > 0
        rate = rates[0]
        assert "timestamp" in rate
        assert "symbol" in rate
        assert "funding_rate" in rate

    def test_signals_latest_with_data(self, client, seeded_db):
        r = client.get("/signals/latest")
        assert r.status_code == 200
        signals = r.json()
        assert len(signals) > 0
        sig = signals[0]
        assert "timestamp" in sig
        assert "model_name" in sig
        assert "prediction" in sig
        assert "position_signal" in sig

    def test_decisions_with_data(self, client, seeded_db):
        r = client.get("/decisions/")
        assert r.status_code == 200
        decisions = r.json()
        assert len(decisions) > 0
        dec = decisions[0]
        assert "timestamp" in dec
        assert "decision" in dec
        assert "direction" in dec
        assert "z_score" in dec
        assert "regime" in dec
        assert "reason" in dec

    def test_positions_with_data(self, client, seeded_db):
        r = client.get("/positions/")
        assert r.status_code == 200
        data = r.json()
        assert data["side"] == "long"
        assert data["entry_price"] > 0

    def test_positions_current_with_data(self, client, seeded_db):
        r = client.get("/positions/current")
        assert r.status_code == 200
        positions = r.json()
        assert len(positions) > 0
        pos = positions[0]
        assert "timestamp" in pos
        assert "side" in pos
        assert "entry_price" in pos
        assert "size" in pos

    def test_analytics_pnl_summary_with_data(self, client, seeded_db):
        r = client.get("/analytics/pnl-summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_trades"] == 5
        assert 0.0 < data["win_rate"] < 1.0
        assert data["total_pnl"] == pytest.approx(325.0, rel=0.01)

    def test_analytics_equity_curve_with_data(self, client, seeded_db):
        r = client.get("/analytics/equity-curve")
        assert r.status_code == 200
        curve = r.json()
        assert len(curve) == 5
        point = curve[0]
        assert "timestamp" in point
        assert "equity" in point

    def test_analytics_performance_with_data(self, client, seeded_db):
        r = client.get("/analytics/performance")
        assert r.status_code == 200
        data = r.json()
        assert data["total_trades"] == 5
        assert "win_rate" in data
        assert "sharpe_ratio" in data
        assert "sortino_ratio" in data
        assert "max_drawdown" in data
        assert "best_trade" in data
        assert "worst_trade" in data
        assert "profit_factor" in data
        assert "expected_value" in data

    def test_metrics_with_data(self, client, seeded_db):
        r = client.get("/metrics/")
        assert r.status_code == 200
        data = r.json()
        assert "today_realized_pnl" in data
        assert "unrealized_pnl" in data
        # unrealized_pnl should be non-None since we seeded a position
        assert data["unrealized_pnl"] is not None

    def test_risk_status_with_data(self, client, seeded_db):
        r = client.get("/risk/status")
        assert r.status_code == 200
        data = r.json()
        assert "current_drawdown_pct" in data
        assert "daily_loss_used_pct" in data
        assert "position_ratio" in data
        assert "consecutive_losses" in data
        assert "risk_level" in data
        assert "high_water_mark" in data
        assert "current_equity" in data
        assert data["risk_level"] in ("low", "medium", "high")

    def test_control_start_stop_idempotency(self, client, seeded_db):
        # Stop first, then start
        client.post("/control/stop")
        r1 = client.post("/control/start")
        assert r1.status_code == 200
        assert r1.json()["success"] is True

        # Starting again should return success=False (already running)
        r2 = client.post("/control/start")
        assert r2.status_code == 200
        assert r2.json()["success"] is False
        assert "already" in r2.json()["message"].lower()

    def test_control_stop_idempotency(self, client, seeded_db):
        client.post("/control/stop")
        r = client.post("/control/stop")
        assert r.status_code == 200
        assert r.json()["success"] is False
        assert "not running" in r.json()["message"].lower()

    def test_control_set_leverage_values(self, client, seeded_db):
        for leverage in [1, 5, 10, 50, 125]:
            r = client.post("/control/set-leverage", json={"leverage": leverage})
            assert r.status_code == 200
            assert r.json()["success"] is True

    def test_models_metrics_structure(self, client, seeded_db):
        r = client.get("/models/metrics")
        assert r.status_code == 200
        data = r.json()
        expected_keys = [
            "last_retrain_at", "next_retrain_at", "ic_history",
            "rank_ic_history", "direction_accuracy", "feature_importance",
            "model_files",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_system_latency_structure(self, client, seeded_db):
        r = client.get("/system/latency")
        assert r.status_code == 200
        data = r.json()
        expected_keys = [
            "data_fetch_ms", "feature_compute_ms", "model_predict_ms",
            "decision_ms", "total_ms", "measured_at",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_system_scheduler_structure(self, client, seeded_db):
        r = client.get("/system/scheduler")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data
        assert "jobs" in data
        assert "next_run" in data
        assert isinstance(data["jobs"], list)
