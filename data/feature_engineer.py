"""Feature engineering for Aegis — 20+ features for crypto futures.

Optimized for 30m/1h timeframes. Compatible with Qlib Alpha158 format.
Includes Futures-specific features: funding_rate, open_interest, etc.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_features(df: pd.DataFrame, funding_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compute all features from OHLCV data.

    Args:
        df: DataFrame with columns [timestamp, open, high, low, close, volume,
            taker_buy_volume, taker_buy_quote_volume, quote_volume]
            Sorted ascending by timestamp.
        funding_df: Optional DataFrame with [timestamp, funding_rate] for futures features.

    Returns:
        DataFrame with all computed features. NaN handled via forward-fill then dropna.
    """
    df = df.copy().sort_values("timestamp").reset_index(drop=True)
    feat = pd.DataFrame(index=df.index)
    feat["timestamp"] = df["timestamp"]

    c = df["close"]
    h = df["high"]
    lo = df["low"]
    v = df["volume"]

    # ------------------------------------------------------------------
    # Momentum / Reversal
    # ------------------------------------------------------------------
    # 30m candles: 1h=2, 4h=8, 12h=24, 24h=48
    feat["return_1h"] = c.pct_change(2)
    feat["return_4h"] = c.pct_change(8)
    feat["return_12h"] = c.pct_change(24)
    feat["return_24h"] = c.pct_change(48)

    roll_std_24h = feat["return_24h"].rolling(48).std()
    feat["return_zscore_24h"] = feat["return_24h"] / roll_std_24h.replace(0, np.nan)

    feat["roc_6"] = c.pct_change(6)
    feat["roc_12"] = c.pct_change(12)
    feat["roc_24"] = c.pct_change(24)

    # ------------------------------------------------------------------
    # Volatility
    # ------------------------------------------------------------------
    log_ret = np.log(c / c.shift(1))
    feat["realized_vol_12h"] = log_ret.rolling(24).std() * np.sqrt(24)
    feat["realized_vol_24h"] = log_ret.rolling(48).std() * np.sqrt(48)

    # ATR-14
    tr = pd.concat([
        h - lo,
        (h - c.shift(1)).abs(),
        (lo - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    feat["atr_14"] = tr.rolling(14).mean()

    # Parkinson volatility (24h)
    log_hl = np.log(h / lo)
    feat["parkinson_vol_24h"] = np.sqrt((log_hl ** 2).rolling(48).mean() / (4 * np.log(2)))

    # Bollinger band width (20)
    bb_mid = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    feat["bollinger_width_20"] = (2 * bb_std) / bb_mid.replace(0, np.nan)

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------
    vol_ma_12h = v.rolling(24).mean()
    feat["volume_ratio_12h"] = v / vol_ma_12h.replace(0, np.nan)

    # VWAP deviation (rolling 24h)
    typical_price = (h + lo + c) / 3
    vwap = (typical_price * v).rolling(48).sum() / v.rolling(48).sum().replace(0, np.nan)
    feat["vwap_deviation"] = (c - vwap) / vwap.replace(0, np.nan)

    # OBV change 12h
    direction = np.sign(c.diff())
    obv = (direction * v).cumsum()
    obv_ma = obv.rolling(24).mean()
    feat["obv_change_12h"] = (obv - obv_ma) / obv_ma.replace(0, np.nan).abs()

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    feat["ema_cross_12_26"] = (ema12 - ema26) / c.replace(0, np.nan)
    feat["macd_histogram"] = (macd_line - macd_signal) / c.replace(0, np.nan)

    # ADX-14
    feat["adx_14"] = _compute_adx(h, lo, c, period=14)

    # ------------------------------------------------------------------
    # Microstructure
    # ------------------------------------------------------------------
    feat["spread_avg_1h"] = (h - lo).rolling(2).mean() / c.replace(0, np.nan)
    feat["high_low_ratio"] = h / lo.replace(0, np.nan)
    hl_range = (h - lo).replace(0, np.nan)
    feat["close_position"] = (c - lo) / hl_range

    # ------------------------------------------------------------------
    # Futures-specific features
    # ------------------------------------------------------------------
    if funding_df is not None and not funding_df.empty:
        funding_df = funding_df.copy().sort_values("timestamp")
        # Merge on nearest timestamp (forward fill)
        merged = pd.merge_asof(
            df[["timestamp"]],
            funding_df[["timestamp", "funding_rate"]].rename(columns={"timestamp": "fr_ts"}),
            left_on="timestamp",
            right_on="fr_ts",
            direction="backward",
        )
        feat["funding_rate"] = merged["funding_rate"].values
        feat["funding_rate_ma_3"] = feat["funding_rate"].rolling(3).mean()
    else:
        feat["funding_rate"] = np.nan
        feat["funding_rate_ma_3"] = np.nan

    # Basis (futures - spot) — placeholder, requires separate spot data
    feat["basis"] = np.nan

    # Open interest change 24h — populated externally if OI data available
    feat["open_interest_change_24h"] = np.nan

    # Long/short ratio — populated externally
    feat["long_short_ratio"] = np.nan

    # Taker buy/sell ratio
    if "taker_buy_volume" in df.columns and "volume" in df.columns:
        taker_buy = pd.to_numeric(df["taker_buy_volume"], errors="coerce")
        total_vol = v.replace(0, np.nan)
        feat["taker_buy_sell_ratio"] = taker_buy / total_vol
    else:
        feat["taker_buy_sell_ratio"] = np.nan

    # ------------------------------------------------------------------
    # NaN handling: forward-fill then drop remaining NaN rows
    # ------------------------------------------------------------------
    feat = feat.ffill()
    feat = feat.dropna().reset_index(drop=True)

    logger.debug("Feature engineering complete: %d rows, %d features", len(feat), len(feat.columns) - 1)
    return feat


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Average Directional Index."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=high.index)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx


FEATURE_COLUMNS = [
    # Momentum
    "return_1h", "return_4h", "return_12h", "return_24h",
    "return_zscore_24h", "roc_6", "roc_12", "roc_24",
    # Volatility
    "realized_vol_12h", "realized_vol_24h", "atr_14",
    "parkinson_vol_24h", "bollinger_width_20",
    # Volume
    "volume_ratio_12h", "vwap_deviation", "obv_change_12h",
    # Trend
    "ema_cross_12_26", "macd_histogram", "adx_14",
    # Microstructure
    "spread_avg_1h", "high_low_ratio", "close_position",
    # Futures
    "funding_rate", "funding_rate_ma_3", "basis",
    "open_interest_change_24h", "long_short_ratio", "taker_buy_sell_ratio",
]
