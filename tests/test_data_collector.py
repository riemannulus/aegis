"""Tests for data pipeline: storage, binance_vision, feature_engineer."""

from __future__ import annotations

import os
import tempfile
import pandas as pd
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_storage(tmp_path):
    from data.storage import Storage
    db_path = str(tmp_path / "test.db")
    return Storage(db_path=db_path)


def test_storage_upsert_candles(tmp_storage):
    rows = [
        {"timestamp": 1000, "symbol": "BTCUSDT", "interval": "30m",
         "open": 50000.0, "high": 51000.0, "low": 49000.0, "close": 50500.0, "volume": 100.0},
        {"timestamp": 2000, "symbol": "BTCUSDT", "interval": "30m",
         "open": 50500.0, "high": 51500.0, "low": 50000.0, "close": 51000.0, "volume": 120.0},
    ]
    inserted = tmp_storage.upsert_candles(rows)
    assert inserted == 2

    # Upsert same rows should not increase count
    inserted2 = tmp_storage.upsert_candles(rows)
    assert inserted2 == 0


def test_storage_get_candles(tmp_storage):
    rows = [
        {"timestamp": i * 1800000, "symbol": "BTCUSDT", "interval": "30m",
         "open": 50000.0, "high": 51000.0, "low": 49000.0, "close": 50500.0, "volume": 100.0}
        for i in range(10)
    ]
    tmp_storage.upsert_candles(rows)
    result = tmp_storage.get_candles(symbol="BTCUSDT", interval="30m")
    assert len(result) == 10
    assert result[0]["timestamp"] == 0


def test_storage_get_latest_timestamp(tmp_storage):
    rows = [
        {"timestamp": i * 1000, "symbol": "BTCUSDT", "interval": "30m",
         "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
        for i in range(5)
    ]
    tmp_storage.upsert_candles(rows)
    latest = tmp_storage.get_latest_candle_timestamp(symbol="BTCUSDT", interval="30m")
    assert latest == 4000


def test_storage_insert_decision(tmp_storage):
    record = {
        "timestamp": 1000,
        "candle_id": 1,
        "decision": "SKIP",
        "direction": "flat",
        "z_score": 0.5,
        "regime": "RANGING",
        "reason": "Signal below threshold",
        "full_record": {"key": "value"},
    }
    tmp_storage.insert_decision(record)
    decisions = tmp_storage.get_decisions(limit=10)
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "SKIP"
    assert isinstance(decisions[0]["full_record"], dict)


def test_storage_insert_trade(tmp_storage):
    trade = {
        "timestamp": 1000,
        "side": "long",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "pnl": 100.0,
        "funding_cost": 5.0,
    }
    tmp_storage.insert_trade(trade)
    trades = tmp_storage.get_trades(limit=10)
    assert len(trades) == 1
    assert trades[0]["pnl"] == 100.0


# ---------------------------------------------------------------------------
# Binance Vision URL generation tests (no network calls)
# ---------------------------------------------------------------------------

def test_binance_vision_monthly_url():
    from data.binance_vision import _monthly_url
    url = _monthly_url("BTCUSDT", "30m", 2024, 1)
    assert "BTCUSDT-30m-2024-01.zip" in url
    assert "futures/um/monthly" in url
    assert "data.binance.vision" in url


def test_binance_vision_daily_url():
    from data.binance_vision import _daily_url
    url = _daily_url("BTCUSDT", "30m", 2024, 1, 15)
    assert "BTCUSDT-30m-2024-01-15.zip" in url
    assert "futures/um/daily" in url


def test_binance_vision_months_in_range():
    from datetime import date
    from data.binance_vision import _months_in_range
    months = list(_months_in_range(date(2024, 1, 1), date(2024, 3, 31)))
    assert months == [(2024, 1), (2024, 2), (2024, 3)]


def test_binance_vision_to_storage_rows():
    from data.binance_vision import to_storage_rows
    df = pd.DataFrame({
        "open_time": [1000, 2000],
        "open": [50000.0, 50100.0],
        "high": [51000.0, 51100.0],
        "low": [49000.0, 49100.0],
        "close": [50500.0, 50600.0],
        "volume": [100.0, 110.0],
        "quote_volume": [5000000.0, 5500000.0],
        "count": [1000, 1100],
        "taker_buy_volume": [50.0, 55.0],
        "taker_buy_quote_volume": [2500000.0, 2750000.0],
    })
    rows = to_storage_rows(df, symbol="BTCUSDT", interval="30m")
    assert len(rows) == 2
    assert rows[0]["timestamp"] == 1000
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["interval"] == "30m"
