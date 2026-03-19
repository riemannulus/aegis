"""
PnL Calculator for Aegis trading system.

Calculates per-trade PnL with leverage, funding costs, and trading fees.
Produces equity curves and benchmark comparison vs BTC Buy&Hold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class TradePnL:
    """Computed PnL for a single trade."""

    trade_id: int
    entry_time: datetime
    exit_time: datetime
    direction: int  # +1 = long, -1 = short
    entry_price: float
    exit_price: float
    size: float  # base asset quantity (BTC)
    leverage: float

    # Costs
    funding_cost: float = 0.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0

    # Computed
    gross_pnl: float = field(init=False)
    trading_fee: float = field(init=False)
    net_pnl: float = field(init=False)
    net_pnl_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self.gross_pnl = (
            (self.exit_price - self.entry_price)
            * self.size
            * self.leverage
            * self.direction
        )
        self.trading_fee = self.entry_fee + self.exit_fee
        self.net_pnl = self.gross_pnl - self.funding_cost - self.trading_fee
        # Net PnL as % of margin (initial margin = entry_price * size / leverage)
        margin = self.entry_price * self.size / self.leverage
        self.net_pnl_pct = self.net_pnl / margin if margin > 0 else 0.0

    @property
    def hold_duration(self) -> pd.Timedelta:
        return pd.Timedelta(self.exit_time - self.entry_time)

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


class PnLCalculator:
    """
    Computes per-trade PnL and aggregations for the Aegis trading system.

    Fees default to Binance Futures maker/taker rates.
    """

    DEFAULT_TAKER_FEE = 0.0004  # 0.04%
    DEFAULT_MAKER_FEE = 0.0002  # 0.02%

    def __init__(
        self,
        taker_fee_rate: float = DEFAULT_TAKER_FEE,
        maker_fee_rate: float = DEFAULT_MAKER_FEE,
    ) -> None:
        self.taker_fee_rate = taker_fee_rate
        self.maker_fee_rate = maker_fee_rate

    # ------------------------------------------------------------------
    # Per-trade PnL
    # ------------------------------------------------------------------

    def compute_trade_pnl(
        self,
        trade_id: int,
        entry_time: datetime,
        exit_time: datetime,
        direction: int,
        entry_price: float,
        exit_price: float,
        size: float,
        leverage: float,
        funding_cost: float = 0.0,
        use_maker_fee: bool = False,
    ) -> TradePnL:
        """
        Compute PnL for a single trade.

        Args:
            direction: +1 for long, -1 for short
            size: base asset quantity (e.g. BTC amount)
            funding_cost: total funding fees paid during hold period
            use_maker_fee: True if limit orders were used (maker fee)
        """
        fee_rate = self.maker_fee_rate if use_maker_fee else self.taker_fee_rate
        entry_fee = entry_price * size * fee_rate
        exit_fee = exit_price * size * fee_rate

        return TradePnL(
            trade_id=trade_id,
            entry_time=entry_time,
            exit_time=exit_time,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            leverage=leverage,
            funding_cost=funding_cost,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
        )

    def compute_trades_pnl(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute PnL for a DataFrame of trades.

        Expected columns:
            trade_id, entry_time, exit_time, direction (±1), entry_price,
            exit_price, size, leverage, funding_cost, use_maker_fee (bool, optional)

        Returns DataFrame with added columns:
            gross_pnl, trading_fee, net_pnl, net_pnl_pct, margin, hold_seconds
        """
        df = trades_df.copy()

        # Direction: +1 long, -1 short
        direction = df["direction"].astype(float)
        gross_pnl = (df["exit_price"] - df["entry_price"]) * df["size"] * df["leverage"] * direction
        df["gross_pnl"] = gross_pnl

        fee_rate = df.get("use_maker_fee", pd.Series([False] * len(df))).map(
            lambda m: self.maker_fee_rate if m else self.taker_fee_rate
        )
        df["entry_fee"] = df["entry_price"] * df["size"] * fee_rate
        df["exit_fee"] = df["exit_price"] * df["size"] * fee_rate
        df["trading_fee"] = df["entry_fee"] + df["exit_fee"]

        funding_cost = df.get("funding_cost", pd.Series([0.0] * len(df)))
        df["funding_cost"] = funding_cost
        df["net_pnl"] = df["gross_pnl"] - df["funding_cost"] - df["trading_fee"]

        margin = df["entry_price"] * df["size"] / df["leverage"]
        df["margin"] = margin
        df["net_pnl_pct"] = df["net_pnl"] / margin.replace(0, np.nan)

        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df["hold_seconds"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds()

        return df

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def daily_pnl(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate net PnL by calendar day (UTC) of exit."""
        df = self.compute_trades_pnl(trades_df)
        df["date"] = df["exit_time"].dt.normalize()
        return (
            df.groupby("date")
            .agg(
                gross_pnl=("gross_pnl", "sum"),
                net_pnl=("net_pnl", "sum"),
                funding_cost=("funding_cost", "sum"),
                trading_fee=("trading_fee", "sum"),
                trade_count=("trade_id", "count"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )

    def weekly_pnl(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate net PnL by ISO week of exit."""
        df = self.compute_trades_pnl(trades_df)
        df["week"] = df["exit_time"].dt.to_period("W")
        return (
            df.groupby("week")
            .agg(
                gross_pnl=("gross_pnl", "sum"),
                net_pnl=("net_pnl", "sum"),
                funding_cost=("funding_cost", "sum"),
                trading_fee=("trading_fee", "sum"),
                trade_count=("trade_id", "count"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )

    def monthly_pnl(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate net PnL by month of exit."""
        df = self.compute_trades_pnl(trades_df)
        df["month"] = df["exit_time"].dt.to_period("M")
        return (
            df.groupby("month")
            .agg(
                gross_pnl=("gross_pnl", "sum"),
                net_pnl=("net_pnl", "sum"),
                funding_cost=("funding_cost", "sum"),
                trading_fee=("trading_fee", "sum"),
                trade_count=("trade_id", "count"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Equity curve
    # ------------------------------------------------------------------

    def equity_curve(
        self,
        trades_df: pd.DataFrame,
        initial_capital: float = 10_000.0,
    ) -> pd.DataFrame:
        """
        Build cumulative equity curve from trade PnLs.

        Returns DataFrame with columns: exit_time, cumulative_pnl, equity.
        """
        df = self.compute_trades_pnl(trades_df).sort_values("exit_time")
        df["cumulative_pnl"] = df["net_pnl"].cumsum()
        df["equity"] = initial_capital + df["cumulative_pnl"]
        return df[["exit_time", "net_pnl", "cumulative_pnl", "equity"]].reset_index(drop=True)

    def btc_buy_hold_alpha(
        self,
        trades_df: pd.DataFrame,
        candles_df: pd.DataFrame,
        initial_capital: float = 10_000.0,
    ) -> pd.DataFrame:
        """
        Compare strategy equity curve against BTC Buy&Hold benchmark.

        Args:
            candles_df: DataFrame with columns [timestamp, close]
            initial_capital: starting USDT capital

        Returns DataFrame with columns:
            timestamp, strategy_equity, btc_equity, alpha
        """
        eq = self.equity_curve(trades_df, initial_capital)
        candles = candles_df.copy()
        candles["timestamp"] = pd.to_datetime(candles["timestamp"])
        candles = candles.sort_values("timestamp").reset_index(drop=True)

        # BTC B&H: buy at first available price
        btc_start_price = candles["close"].iloc[0]
        candles["btc_equity"] = (candles["close"] / btc_start_price) * initial_capital

        # Merge on nearest timestamp
        eq = eq.rename(columns={"exit_time": "timestamp"})
        combined = pd.merge_asof(
            candles[["timestamp", "close", "btc_equity"]],
            eq[["timestamp", "equity"]].rename(columns={"equity": "strategy_equity"}),
            on="timestamp",
            direction="backward",
        )
        combined["strategy_equity"] = combined["strategy_equity"].fillna(initial_capital)
        combined["alpha"] = combined["strategy_equity"] - combined["btc_equity"]
        return combined[["timestamp", "strategy_equity", "btc_equity", "alpha"]]
