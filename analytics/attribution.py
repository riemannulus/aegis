"""
PnL Attribution for Aegis trading system.

Breaks down PnL by:
- Model contribution (LightGBM, TRA, ADARNN)
- Market regime (TRENDING, RANGING, VOLATILE)
- Trade direction (LONG vs SHORT)
- Time-of-day
- Funding cost share and slippage impact
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from analytics.pnl_calculator import PnLCalculator


class Attribution:
    """
    PnL attribution analysis for the Aegis trading system.

    Expected trades_df columns:
        trade_id, direction (+1/-1), net_pnl, gross_pnl,
        funding_cost, trading_fee, entry_price, exit_price,
        entry_time, exit_time, regime,
        lgbm_weight (optional), tra_weight (optional), adarnn_weight (optional),
        intended_price (optional), filled_price (optional)

    If net_pnl/gross_pnl/trading_fee are absent they are computed on the fly
    via PnLCalculator with default fee rates.
    """

    def __init__(self) -> None:
        self._pnl_calc = PnLCalculator()

    def _ensure_pnl(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """Compute PnL columns if they are not already present."""
        if "net_pnl" not in trades_df.columns:
            return self._pnl_calc.compute_trades_pnl(trades_df)
        return trades_df

    MODELS = ["lgbm", "tra", "adarnn"]
    REGIMES = ["TRENDING", "RANGING", "VOLATILE"]

    # ------------------------------------------------------------------
    # Model contribution
    # ------------------------------------------------------------------

    def model_contribution(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute per-model contribution to each trade's net PnL.

        Uses ensemble weight columns (lgbm_weight, tra_weight, adarnn_weight)
        to attribute net PnL proportionally. Falls back to equal weights if
        weight columns are absent.

        Returns DataFrame with columns:
            trade_id, model, weight, attributed_pnl
        """
        df = self._ensure_pnl(trades_df)
        records = []

        weight_cols = {
            "lgbm": "lgbm_weight",
            "tra": "tra_weight",
            "adarnn": "adarnn_weight",
        }

        for _, row in df.iterrows():
            weights = {}
            for model, col in weight_cols.items():
                weights[model] = float(row.get(col, 1.0 / 3))

            total_w = sum(weights.values())
            for model, w in weights.items():
                norm_w = w / total_w if total_w > 0 else 1.0 / 3
                records.append(
                    {
                        "trade_id": row["trade_id"],
                        "model": model,
                        "weight": norm_w,
                        "attributed_pnl": row["net_pnl"] * norm_w,
                    }
                )

        result = pd.DataFrame(records)
        return result

    def model_contribution_summary(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate model contributions across all trades.

        Returns DataFrame with columns: model, total_attributed_pnl, avg_weight.
        """
        detail = self.model_contribution(trades_df)
        summary = (
            detail.groupby("model")
            .agg(
                total_attributed_pnl=("attributed_pnl", "sum"),
                avg_weight=("weight", "mean"),
                trade_count=("trade_id", "count"),
            )
            .reset_index()
        )
        return summary

    # ------------------------------------------------------------------
    # Regime performance
    # ------------------------------------------------------------------

    def regime_performance(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down performance by market regime.

        Returns DataFrame with columns:
            regime, trade_count, total_net_pnl, win_rate, avg_net_pnl
        """
        df = self._ensure_pnl(trades_df)
        if "regime" not in df.columns:
            df["regime"] = "UNKNOWN"

        result = (
            df.groupby("regime")
            .agg(
                trade_count=("net_pnl", "count"),
                total_net_pnl=("net_pnl", "sum"),
                avg_net_pnl=("net_pnl", "mean"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )
        result["win_rate"] = result["win_count"] / result["trade_count"]
        return result.drop(columns=["win_count"])

    # ------------------------------------------------------------------
    # Direction performance
    # ------------------------------------------------------------------

    def direction_performance(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compare LONG vs SHORT trade performance.

        Returns DataFrame with columns:
            direction_label, trade_count, total_net_pnl, win_rate, avg_net_pnl
        """
        df = self._ensure_pnl(trades_df)
        df["direction_label"] = df["direction"].map({1: "LONG", -1: "SHORT"}).fillna("UNKNOWN")

        result = (
            df.groupby("direction_label")
            .agg(
                trade_count=("net_pnl", "count"),
                total_net_pnl=("net_pnl", "sum"),
                avg_net_pnl=("net_pnl", "mean"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )
        result["win_rate"] = result["win_count"] / result["trade_count"]
        return result.drop(columns=["win_count"])

    # ------------------------------------------------------------------
    # Time-of-day performance
    # ------------------------------------------------------------------

    def time_of_day_performance(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down performance by UTC hour of trade entry.

        Returns DataFrame with columns:
            hour, trade_count, total_net_pnl, avg_net_pnl, win_rate
        """
        df = self._ensure_pnl(trades_df)
        df["entry_time"] = pd.to_datetime(df["entry_time"])
        df["hour"] = df["entry_time"].dt.hour

        result = (
            df.groupby("hour")
            .agg(
                trade_count=("net_pnl", "count"),
                total_net_pnl=("net_pnl", "sum"),
                avg_net_pnl=("net_pnl", "mean"),
                win_count=("net_pnl", lambda x: (x > 0).sum()),
            )
            .reset_index()
        )
        result["win_rate"] = result["win_count"] / result["trade_count"]
        result = result.drop(columns=["win_count"])

        # Fill missing hours
        all_hours = pd.DataFrame({"hour": range(24)})
        result = all_hours.merge(result, on="hour", how="left").fillna(0)
        return result

    # ------------------------------------------------------------------
    # Cost attribution
    # ------------------------------------------------------------------

    def funding_cost_share(self, trades_df: pd.DataFrame) -> dict:
        """
        Compute funding cost as a fraction of gross PnL.

        Returns dict with keys:
            total_gross_pnl, total_funding_cost, funding_share_pct,
            total_trading_fee, fee_share_pct
        """
        df = self._ensure_pnl(trades_df)
        total_gross = float(df["gross_pnl"].sum())
        total_funding = float(df["funding_cost"].sum())
        total_fee = float(df["trading_fee"].sum())

        return {
            "total_gross_pnl": total_gross,
            "total_funding_cost": total_funding,
            "funding_share_pct": (total_funding / abs(total_gross) * 100) if total_gross != 0 else float("nan"),
            "total_trading_fee": total_fee,
            "fee_share_pct": (total_fee / abs(total_gross) * 100) if total_gross != 0 else float("nan"),
        }

    def slippage_impact(self, trades_df: pd.DataFrame) -> dict:
        """
        Compute slippage impact on PnL.

        Requires columns: intended_price, filled_price, size, direction.

        Returns dict with keys:
            total_slippage_usdt, avg_slippage_bps, slippage_pnl_share_pct
        """
        df = self._ensure_pnl(trades_df)
        if "intended_price" not in df.columns or "filled_price" not in df.columns:
            return {
                "total_slippage_usdt": float("nan"),
                "avg_slippage_bps": float("nan"),
                "slippage_pnl_share_pct": float("nan"),
            }

        # Slippage: difference between intended and filled, adjusted for direction
        # Long: fills higher than intended → negative slippage
        # Short: fills lower than intended → negative slippage
        slip_price = (df["filled_price"] - df["intended_price"]) * df["direction"]
        slip_usdt = slip_price * df["size"]
        slip_bps = (df["filled_price"] - df["intended_price"]).abs() / df["intended_price"] * 10_000

        total_slip_usdt = float(slip_usdt.sum())
        avg_slip_bps = float(slip_bps.mean())
        total_net = float(df["net_pnl"].sum())

        return {
            "total_slippage_usdt": total_slip_usdt,
            "avg_slippage_bps": avg_slip_bps,
            "slippage_pnl_share_pct": (abs(total_slip_usdt) / abs(total_net) * 100)
            if total_net != 0
            else float("nan"),
        }

    # ------------------------------------------------------------------
    # Full attribution report
    # ------------------------------------------------------------------

    def full_attribution(self, trades_df: pd.DataFrame) -> dict:
        """
        Run all attribution analyses and return as a dict of DataFrames/dicts.
        """
        return {
            "model_contribution": self.model_contribution_summary(trades_df),
            "regime_performance": self.regime_performance(trades_df),
            "direction_performance": self.direction_performance(trades_df),
            "time_of_day_performance": self.time_of_day_performance(trades_df),
            "funding_cost_share": self.funding_cost_share(trades_df),
            "slippage_impact": self.slippage_impact(trades_df),
        }
