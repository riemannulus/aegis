"""
Performance Metrics for Aegis trading system.

Computes Sharpe, Sortino, Calmar, win rate, profit factor, expected value,
consecutive win/loss streaks, hourly heatmap, and day-of-week distribution.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


class PerformanceMetrics:
    """
    Computes risk-adjusted performance metrics from trade-level PnL data.

    All ratios are annualized unless otherwise noted.
    Assumes 30-minute candles: 17520 periods/year (365 * 48).
    """

    PERIODS_PER_YEAR_30M = 365 * 48  # 17520
    PERIODS_PER_YEAR_1H = 365 * 24   # 8760
    PERIODS_PER_YEAR_DAILY = 365

    def __init__(self, periods_per_year: int = PERIODS_PER_YEAR_30M) -> None:
        self.periods_per_year = periods_per_year

    # ------------------------------------------------------------------
    # Core ratio metrics
    # ------------------------------------------------------------------

    def sharpe_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: float = 0.0,
    ) -> float:
        """
        Annualized Sharpe ratio.

        Args:
            returns: per-period returns (not cumulative)
            risk_free_rate: annualized risk-free rate (default 0)
        """
        if len(returns) < 2:
            return float("nan")
        excess = returns - risk_free_rate / self.periods_per_year
        std = excess.std(ddof=1)
        if std == 0:
            return float("nan")
        return float(excess.mean() / std * math.sqrt(self.periods_per_year))

    def sortino_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: float = 0.0,
        min_acceptable_return: float = 0.0,
    ) -> float:
        """
        Annualized Sortino ratio (penalizes only downside volatility).

        Args:
            min_acceptable_return: MAR per period (default 0)
        """
        if len(returns) < 2:
            return float("nan")
        excess = returns - risk_free_rate / self.periods_per_year
        downside = excess[excess < min_acceptable_return]
        if len(downside) == 0:
            return float("inf")
        downside_std = math.sqrt((downside**2).mean())
        if downside_std == 0:
            return float("nan")
        return float(excess.mean() / downside_std * math.sqrt(self.periods_per_year))

    def calmar_ratio(
        self,
        returns: pd.Series,
        max_drawdown: Optional[float] = None,
    ) -> float:
        """
        Annualized Calmar ratio = annualized return / max drawdown.

        Args:
            max_drawdown: absolute max drawdown value (positive number).
                          If None, computed from returns.
        """
        if len(returns) < 2:
            return float("nan")
        ann_return = returns.mean() * self.periods_per_year
        if max_drawdown is None:
            max_drawdown = self._max_drawdown_from_returns(returns)
        if max_drawdown == 0:
            return float("inf")
        return float(ann_return / max_drawdown)

    def _max_drawdown_from_returns(self, returns: pd.Series) -> float:
        equity = (1 + returns).cumprod()
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max
        return float(-drawdown.min())

    # ------------------------------------------------------------------
    # Trade statistics
    # ------------------------------------------------------------------

    def win_rate(self, net_pnls: pd.Series) -> float:
        """Fraction of trades with positive net PnL."""
        if len(net_pnls) == 0:
            return float("nan")
        return float((net_pnls > 0).sum() / len(net_pnls))

    def profit_factor(self, net_pnls: pd.Series) -> float:
        """Gross profit / gross loss. Returns inf if no losses."""
        gross_profit = net_pnls[net_pnls > 0].sum()
        gross_loss = net_pnls[net_pnls < 0].abs().sum()
        if gross_loss == 0:
            return float("inf")
        return float(gross_profit / gross_loss)

    def avg_hold_time(self, hold_seconds: pd.Series) -> float:
        """Average hold time in hours."""
        if len(hold_seconds) == 0:
            return float("nan")
        return float(hold_seconds.mean() / 3600)

    def avg_win(self, net_pnls: pd.Series) -> float:
        """Average PnL of winning trades."""
        wins = net_pnls[net_pnls > 0]
        return float(wins.mean()) if len(wins) > 0 else float("nan")

    def avg_loss(self, net_pnls: pd.Series) -> float:
        """Average PnL of losing trades (negative value)."""
        losses = net_pnls[net_pnls < 0]
        return float(losses.mean()) if len(losses) > 0 else float("nan")

    def expected_value(self, net_pnls: pd.Series) -> float:
        """
        Expected value = win_rate * avg_win + loss_rate * avg_loss.
        """
        if len(net_pnls) == 0:
            return float("nan")
        wr = self.win_rate(net_pnls)
        lr = 1.0 - wr
        avg_w = self.avg_win(net_pnls)
        avg_l = self.avg_loss(net_pnls)
        if math.isnan(avg_w):
            avg_w = 0.0
        if math.isnan(avg_l):
            avg_l = 0.0
        return float(wr * avg_w + lr * avg_l)

    def max_consecutive_wins(self, net_pnls: pd.Series) -> int:
        """Maximum number of consecutive winning trades."""
        return self._max_streak(net_pnls > 0)

    def max_consecutive_losses(self, net_pnls: pd.Series) -> int:
        """Maximum number of consecutive losing trades."""
        return self._max_streak(net_pnls < 0)

    def _max_streak(self, mask: pd.Series) -> int:
        max_streak = 0
        current = 0
        for val in mask:
            if val:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    # ------------------------------------------------------------------
    # Time-based distributions
    # ------------------------------------------------------------------

    def hourly_return_heatmap(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute average net PnL grouped by UTC hour of exit.

        Args:
            trades_df: must have columns [exit_time, net_pnl]

        Returns DataFrame indexed 0-23 with columns: hour, avg_net_pnl, trade_count.
        """
        df = trades_df.copy()
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df["hour"] = df["exit_time"].dt.hour
        result = (
            df.groupby("hour")
            .agg(avg_net_pnl=("net_pnl", "mean"), trade_count=("net_pnl", "count"))
            .reset_index()
        )
        # Fill missing hours
        all_hours = pd.DataFrame({"hour": range(24)})
        result = all_hours.merge(result, on="hour", how="left").fillna(0)
        return result

    def day_of_week_distribution(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute average net PnL grouped by day of week (0=Monday) of exit.

        Returns DataFrame with columns: day_of_week, day_name, avg_net_pnl, trade_count.
        """
        df = trades_df.copy()
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df["day_of_week"] = df["exit_time"].dt.dayofweek
        result = (
            df.groupby("day_of_week")
            .agg(avg_net_pnl=("net_pnl", "mean"), trade_count=("net_pnl", "count"))
            .reset_index()
        )
        day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        all_days = pd.DataFrame({"day_of_week": range(7)})
        result = all_days.merge(result, on="day_of_week", how="left").fillna(0)
        result["day_name"] = result["day_of_week"].map(day_names)
        return result

    # ------------------------------------------------------------------
    # Summary report
    # ------------------------------------------------------------------

    def full_summary(
        self,
        trades_df: pd.DataFrame,
        period_returns: Optional[pd.Series] = None,
    ) -> dict:
        """
        Compute all metrics and return as a dict.

        Args:
            trades_df: must have columns [exit_time, net_pnl, hold_seconds]
            period_returns: optional per-period return series for ratio calculations.
                            If None, uses net_pnl_pct per trade as proxy.
        """
        net_pnls = trades_df["net_pnl"]
        hold_seconds = trades_df.get("hold_seconds", pd.Series(dtype=float))

        if period_returns is None:
            period_returns = trades_df.get("net_pnl_pct", net_pnls)

        max_dd = self._max_drawdown_from_returns(period_returns)

        return {
            "total_trades": len(net_pnls),
            "total_net_pnl": float(net_pnls.sum()),
            "win_rate": self.win_rate(net_pnls),
            "profit_factor": self.profit_factor(net_pnls),
            "avg_win": self.avg_win(net_pnls),
            "avg_loss": self.avg_loss(net_pnls),
            "expected_value": self.expected_value(net_pnls),
            "avg_hold_time_h": self.avg_hold_time(hold_seconds),
            "max_consecutive_wins": self.max_consecutive_wins(net_pnls),
            "max_consecutive_losses": self.max_consecutive_losses(net_pnls),
            "sharpe_ratio": self.sharpe_ratio(period_returns),
            "sortino_ratio": self.sortino_ratio(period_returns),
            "calmar_ratio": self.calmar_ratio(period_returns, max_drawdown=max_dd),
            "max_drawdown": max_dd,
        }
