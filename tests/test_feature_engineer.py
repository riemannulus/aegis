"""Tests for feature engineering — 20+ features, no NaN."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.feature_engineer import compute_features, FEATURE_COLUMNS


def _make_candles(n: int = 200) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    close = 50000.0 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = close + np.random.randn(n) * 30
    volume = np.abs(np.random.randn(n) * 1000 + 5000)
    taker_buy = volume * (0.4 + np.random.rand(n) * 0.2)

    timestamps = [i * 1_800_000 for i in range(n)]  # 30min intervals in ms

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy_volume": taker_buy,
        "taker_buy_quote_volume": taker_buy * close,
        "quote_volume": volume * close,
    })


def _make_funding_df(n: int = 30) -> pd.DataFrame:
    timestamps = [i * 28_800_000 for i in range(n)]  # 8h intervals
    return pd.DataFrame({
        "timestamp": timestamps,
        "funding_rate": np.random.randn(n) * 0.0005,
    })


def test_compute_features_no_nan():
    df = _make_candles(200)
    feat = compute_features(df)
    # After dropna there should be no NaN in any numeric column
    numeric_cols = feat.select_dtypes(include=[np.number]).columns
    assert feat[numeric_cols].isnull().sum().sum() == 0, "Feature matrix contains NaN values"


def test_compute_features_minimum_count():
    df = _make_candles(200)
    feat = compute_features(df)
    # Must have at least 20 features (excluding timestamp)
    feature_cols = [c for c in feat.columns if c != "timestamp"]
    assert len(feature_cols) >= 20, f"Only {len(feature_cols)} features computed"


def test_compute_features_with_funding():
    df = _make_candles(200)
    funding_df = _make_funding_df(30)
    feat = compute_features(df, funding_df=funding_df)
    assert "funding_rate" in feat.columns
    assert "funding_rate_ma_3" in feat.columns
    # funding_rate should not be all NaN after merge
    non_nan = feat["funding_rate"].notna().sum()
    assert non_nan > 0


def test_compute_features_momentum():
    df = _make_candles(200)
    feat = compute_features(df)
    for col in ["return_1h", "return_4h", "return_12h", "return_24h"]:
        assert col in feat.columns, f"Missing momentum feature: {col}"


def test_compute_features_volatility():
    df = _make_candles(200)
    feat = compute_features(df)
    for col in ["realized_vol_12h", "realized_vol_24h", "atr_14", "bollinger_width_20"]:
        assert col in feat.columns, f"Missing volatility feature: {col}"


def test_compute_features_volume():
    df = _make_candles(200)
    feat = compute_features(df)
    for col in ["volume_ratio_12h", "vwap_deviation", "obv_change_12h"]:
        assert col in feat.columns, f"Missing volume feature: {col}"


def test_compute_features_trend():
    df = _make_candles(200)
    feat = compute_features(df)
    for col in ["ema_cross_12_26", "macd_histogram", "adx_14"]:
        assert col in feat.columns, f"Missing trend feature: {col}"


def test_compute_features_taker_ratio():
    df = _make_candles(200)
    feat = compute_features(df)
    assert "taker_buy_sell_ratio" in feat.columns
    # Should be between 0 and 1
    valid = feat["taker_buy_sell_ratio"].dropna()
    assert (valid >= 0).all() and (valid <= 1).all()


def test_compute_features_sorted_by_timestamp():
    df = _make_candles(200)
    # Shuffle input
    df_shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
    feat = compute_features(df_shuffled)
    assert feat["timestamp"].is_monotonic_increasing
