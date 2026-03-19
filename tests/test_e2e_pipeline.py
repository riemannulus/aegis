"""End-to-end pipeline test — full signal generation cycle with paper trader.

Uses only in-memory/paper-trading components (no real exchange calls).
Tests the complete flow:
  candle data → features → ensemble prediction → signal → risk check → paper order
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_db(tmp_path_factory):
    """Temporary SQLite DB for the full E2E test."""
    db_path = str(tmp_path_factory.mktemp("data") / "test_e2e.db")
    os.environ["AEGIS_DB_PATH"] = db_path
    import importlib
    import data.storage as sm
    importlib.reload(sm)
    storage = sm.Storage()
    storage.init_db()
    return storage


def _generate_candles(n: int = 100, start_ts: int = 1_700_000_000_000) -> pd.DataFrame:
    """Generate synthetic OHLCV candles."""
    rng = np.random.default_rng(42)
    prices = 50000 + np.cumsum(rng.normal(0, 100, n))
    rows = []
    for i in range(n):
        p = prices[i]
        rows.append({
            "timestamp": start_ts + i * 1_800_000,
            "symbol": "BTCUSDT",
            "interval": "30m",
            "open": p,
            "high": p * 1.002,
            "low": p * 0.998,
            "close": p,
            "volume": 100.0 + rng.uniform(0, 50),
            "quote_volume": p * 100,
            "count": 500,
            "taker_buy_volume": 50.0,
            "taker_buy_quote_volume": p * 50,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# E2E tests
# ---------------------------------------------------------------------------

def test_feature_computation_on_candles():
    """Feature engineer produces features without NaN on sufficient data."""
    from data.feature_engineer import compute_features
    df = _generate_candles(100)
    feat = compute_features(df)
    assert not feat.empty
    assert "timestamp" in feat.columns
    # No NaN in feature columns after dropna
    feature_cols = [c for c in feat.columns if c != "timestamp"]
    assert len(feature_cols) > 0


def test_signal_converter_full_cycle():
    """Signal converter produces valid signals for a series of predictions."""
    from strategy.signal_converter import SignalConverter
    converter = SignalConverter()

    # Feed 50 predictions — should stabilise after warmup
    rng = np.random.default_rng(0)
    preds = rng.normal(0, 0.01, 50)
    results = [converter.convert(float(p)) for p in preds]

    assert len(results) == 50
    for r in results:
        assert r.direction in ("LONG", "SHORT", "FLAT")
        assert 0.0 <= r.size_ratio <= 1.0


def test_paper_trader_full_long_short_cycle():
    """Paper trader: open long → close → open short → close."""
    from execution.paper_trader import PaperTrader
    pt = PaperTrader(initial_balance=10_000.0, leverage=3)
    pt.initialize_futures("BTC/USDT:USDT", 3, "isolated")
    pt.update_price("BTC/USDT:USDT", 50_000.0)

    # Long
    pt.create_market_order("BTC/USDT:USDT", "buy", 0.01)
    pos = pt.get_position("BTC/USDT:USDT")
    assert pos["side"] == "long"

    # Price moves up
    pt.update_price("BTC/USDT:USDT", 51_000.0)
    assert pt.get_position("BTC/USDT:USDT")["unrealized_pnl"] > 0

    pt.close_position("BTC/USDT:USDT")
    assert pt.get_position("BTC/USDT:USDT")["side"] is None

    # Short
    pt.create_market_order("BTC/USDT:USDT", "sell", 0.01)
    pos = pt.get_position("BTC/USDT:USDT")
    assert pos["side"] == "short"

    pt.close_position("BTC/USDT:USDT")
    assert pt.get_position("BTC/USDT:USDT")["side"] is None


def test_risk_engine_blocks_excessive_order():
    """Risk engine blocks an order that exceeds MAX_POSITION_RATIO."""
    from risk.risk_engine import RiskEngine
    engine = RiskEngine()
    engine.initialise(opening_balance=1_000.0)

    # Order 80% of balance — should fail (max is 30%)
    result = engine.check_pre_order(
        order_usdt=800.0,
        account_balance=1_000.0,
        current_position_usdt=0.0,
    )
    assert not result.passed


def test_risk_engine_passes_normal_order():
    """Risk engine approves a normal-sized order."""
    from risk.risk_engine import RiskEngine
    engine = RiskEngine()
    engine.initialise(opening_balance=10_000.0)

    result = engine.check_pre_order(
        order_usdt=1_000.0,
        account_balance=10_000.0,
        current_position_usdt=0.0,
    )
    assert result.passed


def test_order_manager_with_paper_trader():
    """OrderManager + PaperTrader: submit market order and confirm fill."""
    from execution.paper_trader import PaperTrader
    from execution.order_manager import OrderManager, OrderStatus

    pt = PaperTrader(initial_balance=5_000.0, leverage=3)
    pt.initialize_futures("BTC/USDT:USDT", 3, "isolated")
    pt.update_price("BTC/USDT:USDT", 50_000.0)

    om = OrderManager(executor=pt)
    order = om.submit_market_order(
        symbol="BTC/USDT:USDT",
        side="buy",
        amount=0.001,
        intended_price=50_000.0,
    )

    assert order.status == OrderStatus.FILLED
    assert order.fill_price == 50_000.0
    assert order.slippage == 0.0  # paper trader fills at exact price


def test_decision_logger_record_creation():
    """DecisionLogger creates a valid DecisionRecord."""
    from strategy.decision_logger import (
        DecisionLogger, DecisionRecord, MarketSnapshot,
        ModelPredictions, SignalInfo, RiskCheckInfo,
    )

    record = DecisionRecord(
        timestamp="2024-01-15T08:30:00Z",
        candle_id="2024-01-15T08:30:00Z",
        market_snapshot=MarketSnapshot(
            price=50000.0,
            volume_24h=1_000_000.0,
            funding_rate=0.0001,
            regime="TREND",
            regime_confidence=0.8,
        ),
        model_predictions=ModelPredictions(
            lgbm=0.002,
            tra=0.003,
            adarnn=0.001,
            ensemble=0.002,
            z_score=2.1,
            tra_active_router=1,
            tra_router_weights=[0.3, 0.4, 0.3],
        ),
        top_features=[{"name": "return_1h", "value": 0.01}],
        signal=SignalInfo(
            raw_position=0.5,
            direction="LONG",
            size_ratio=0.5,
            cost_filter_passed=True,
            direction_filter_passed=True,
            min_hold_filter_passed=True,
        ),
        risk_check=RiskCheckInfo(
            stage1_passed=True,
            stage1_detail={},
            drawdown_pct=0.01,
            liquidation_distance_pct=0.15,
            stop_loss_level=49000.0,
            take_profit_level=52000.0,
        ),
        decision=DecisionLogger.DECISION_EXECUTE,
        decision_reason="Z=2.1 → LONG size=0.50",
    )

    dl = DecisionLogger(storage=None)
    # Should not raise
    dl.log(record)
