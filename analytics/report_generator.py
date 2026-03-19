"""
Report Generator for Aegis trading system.

Generates daily/weekly/monthly Markdown reports suitable for
Telegram delivery or file export.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd

from analytics.pnl_calculator import PnLCalculator
from analytics.performance_metrics import PerformanceMetrics
from analytics.attribution import Attribution


class ReportGenerator:
    """
    Generates Markdown performance reports from trade data.

    Reports are structured for both file export and Telegram messaging.
    Telegram messages are split into chunks ≤4096 chars when needed.
    """

    TELEGRAM_MAX_CHARS = 4096

    def __init__(
        self,
        pnl_calc: Optional[PnLCalculator] = None,
        perf_metrics: Optional[PerformanceMetrics] = None,
        attribution: Optional[Attribution] = None,
        initial_capital: float = 10_000.0,
        symbol: str = "BTC/USDT:USDT",
        environment: str = "TESTNET",
    ) -> None:
        self.pnl_calc = pnl_calc or PnLCalculator()
        self.perf = perf_metrics or PerformanceMetrics()
        self.attr = attribution or Attribution()
        self.initial_capital = initial_capital
        self.symbol = symbol
        self.environment = environment

    # ------------------------------------------------------------------
    # Daily report
    # ------------------------------------------------------------------

    def daily_report(
        self,
        trades_df: pd.DataFrame,
        report_date: Optional[datetime] = None,
    ) -> str:
        """
        Generate a daily performance report in Markdown.

        Args:
            trades_df: all trades (will filter to report_date)
            report_date: UTC date to report on (default: yesterday)
        """
        if report_date is None:
            report_date = datetime.now(timezone.utc) - timedelta(days=1)

        day_str = report_date.strftime("%Y-%m-%d")

        df = self._filter_by_date(trades_df, report_date, "daily")
        env_tag = f"[{self.environment}]"

        if df.empty:
            return (
                f"# Aegis Daily Report {env_tag}\n"
                f"**Date:** {day_str}\n\n"
                "_No trades executed on this date._\n"
            )

        df = self.pnl_calc.compute_trades_pnl(df)
        net_pnls = df["net_pnl"]
        summary = self.perf.full_summary(df)

        # Risk attribution
        attr = self.attr.full_attribution(df)
        funding = attr["funding_cost_share"]
        direction_perf = attr["direction_performance"]

        lines = [
            f"# Aegis Daily Report {env_tag}",
            f"**Date:** {day_str} | **Symbol:** {self.symbol}",
            "",
            "## PnL Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Gross PnL | {df['gross_pnl'].sum():.2f} USDT |",
            f"| Funding Cost | -{df['funding_cost'].sum():.2f} USDT |",
            f"| Trading Fees | -{df['trading_fee'].sum():.2f} USDT |",
            f"| **Net PnL** | **{net_pnls.sum():.2f} USDT** |",
            "",
            "## Trade Statistics",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Trades | {summary['total_trades']} |",
            f"| Win Rate | {summary['win_rate']:.1%} |",
            f"| Profit Factor | {self._fmt_ratio(summary['profit_factor'])} |",
            f"| Avg Win | {self._fmt_usdt(summary['avg_win'])} |",
            f"| Avg Loss | {self._fmt_usdt(summary['avg_loss'])} |",
            f"| Expected Value | {self._fmt_usdt(summary['expected_value'])} |",
            f"| Avg Hold Time | {summary['avg_hold_time_h']:.1f}h |",
            f"| Max Consec. Wins | {summary['max_consecutive_wins']} |",
            f"| Max Consec. Losses | {summary['max_consecutive_losses']} |",
            "",
            "## Direction Breakdown",
        ]

        lines += self._direction_table(direction_perf)

        lines += [
            "",
            "## Cost Attribution",
            f"- Funding cost share: {self._fmt_pct(funding['funding_share_pct'])}",
            f"- Trading fee share: {self._fmt_pct(funding['fee_share_pct'])}",
            "",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Weekly report
    # ------------------------------------------------------------------

    def weekly_report(
        self,
        trades_df: pd.DataFrame,
        week_start: Optional[datetime] = None,
        candles_df: Optional[pd.DataFrame] = None,
    ) -> str:
        """
        Generate a weekly performance report in Markdown.

        Args:
            week_start: Monday of the ISO week to report (default: last week)
            candles_df: optional candle data for BTC benchmark comparison
        """
        if week_start is None:
            today = datetime.now(timezone.utc)
            week_start = today - timedelta(days=today.weekday() + 7)
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        week_end = week_start + timedelta(days=7)
        week_str = f"{week_start.strftime('%Y-%m-%d')} – {week_end.strftime('%Y-%m-%d')}"
        env_tag = f"[{self.environment}]"

        df = self._filter_by_date_range(trades_df, week_start, week_end)

        if df.empty:
            return (
                f"# Aegis Weekly Report {env_tag}\n"
                f"**Week:** {week_str}\n\n"
                "_No trades executed this week._\n"
            )

        df = self.pnl_calc.compute_trades_pnl(df)
        net_pnls = df["net_pnl"]
        summary = self.perf.full_summary(df)
        attr = self.attr.full_attribution(df)
        regime_perf = attr["regime_performance"]
        direction_perf = attr["direction_performance"]
        model_contrib = attr["model_contribution"]
        funding = attr["funding_cost_share"]
        slippage = attr["slippage_impact"]

        lines = [
            f"# Aegis Weekly Report {env_tag}",
            f"**Week:** {week_str} | **Symbol:** {self.symbol}",
            "",
            "## PnL Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Gross PnL | {df['gross_pnl'].sum():.2f} USDT |",
            f"| Funding Cost | -{df['funding_cost'].sum():.2f} USDT |",
            f"| Trading Fees | -{df['trading_fee'].sum():.2f} USDT |",
            f"| **Net PnL** | **{net_pnls.sum():.2f} USDT** |",
            "",
            "## Risk-Adjusted Metrics",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Sharpe Ratio | {self._fmt_ratio(summary['sharpe_ratio'])} |",
            f"| Sortino Ratio | {self._fmt_ratio(summary['sortino_ratio'])} |",
            f"| Calmar Ratio | {self._fmt_ratio(summary['calmar_ratio'])} |",
            f"| Max Drawdown | {summary['max_drawdown']:.2%} |",
            f"| Win Rate | {summary['win_rate']:.1%} |",
            f"| Profit Factor | {self._fmt_ratio(summary['profit_factor'])} |",
            "",
            "## Regime Performance",
        ]

        lines += self._regime_table(regime_perf)

        lines += ["", "## Direction Breakdown"]
        lines += self._direction_table(direction_perf)

        lines += ["", "## Model Contribution"]
        lines += self._model_table(model_contrib)

        lines += [
            "",
            "## Cost Analysis",
            f"- Funding cost share: {self._fmt_pct(funding['funding_share_pct'])}",
            f"- Trading fee share: {self._fmt_pct(funding['fee_share_pct'])}",
            f"- Avg slippage: {self._fmt_bps(slippage['avg_slippage_bps'])}",
        ]

        if candles_df is not None and not candles_df.empty:
            alpha_df = self.pnl_calc.btc_buy_hold_alpha(df, candles_df, self.initial_capital)
            if not alpha_df.empty:
                strategy_ret = (alpha_df["strategy_equity"].iloc[-1] - self.initial_capital) / self.initial_capital
                btc_ret = (alpha_df["btc_equity"].iloc[-1] - self.initial_capital) / self.initial_capital
                lines += [
                    "",
                    "## vs BTC Buy&Hold",
                    f"| | Return |",
                    f"|---|---|",
                    f"| Strategy | {strategy_ret:.2%} |",
                    f"| BTC B&H | {btc_ret:.2%} |",
                    f"| **Alpha** | **{strategy_ret - btc_ret:.2%}** |",
                ]

        lines += [
            "",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Monthly report
    # ------------------------------------------------------------------

    def monthly_report(
        self,
        trades_df: pd.DataFrame,
        year: Optional[int] = None,
        month: Optional[int] = None,
        candles_df: Optional[pd.DataFrame] = None,
    ) -> str:
        """
        Generate a monthly performance report in Markdown.

        Args:
            year: UTC year (default: last month's year)
            month: UTC month 1-12 (default: last month)
            candles_df: optional candle data for BTC benchmark comparison
        """
        today = datetime.now(timezone.utc)
        if month is None or year is None:
            first_of_month = today.replace(day=1)
            last_month = first_of_month - timedelta(days=1)
            year = last_month.year
            month = last_month.month

        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        month_str = month_start.strftime("%B %Y")
        env_tag = f"[{self.environment}]"

        df = self._filter_by_date_range(trades_df, month_start, month_end)

        if df.empty:
            return (
                f"# Aegis Monthly Report {env_tag}\n"
                f"**Month:** {month_str}\n\n"
                "_No trades executed this month._\n"
            )

        df = self.pnl_calc.compute_trades_pnl(df)
        net_pnls = df["net_pnl"]
        summary = self.perf.full_summary(df)
        daily = self.pnl_calc.daily_pnl(df)
        attr = self.attr.full_attribution(df)
        regime_perf = attr["regime_performance"]
        direction_perf = attr["direction_performance"]
        model_contrib = attr["model_contribution"]
        funding = attr["funding_cost_share"]
        slippage = attr["slippage_impact"]

        lines = [
            f"# Aegis Monthly Report {env_tag}",
            f"**Month:** {month_str} | **Symbol:** {self.symbol}",
            "",
            "## PnL Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Gross PnL | {df['gross_pnl'].sum():.2f} USDT |",
            f"| Funding Cost | -{df['funding_cost'].sum():.2f} USDT |",
            f"| Trading Fees | -{df['trading_fee'].sum():.2f} USDT |",
            f"| **Net PnL** | **{net_pnls.sum():.2f} USDT** |",
            f"| Trading Days | {daily['date'].nunique() if not daily.empty else 0} |",
            f"| Total Trades | {summary['total_trades']} |",
            "",
            "## Risk-Adjusted Metrics",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Sharpe Ratio (ann.) | {self._fmt_ratio(summary['sharpe_ratio'])} |",
            f"| Sortino Ratio (ann.) | {self._fmt_ratio(summary['sortino_ratio'])} |",
            f"| Calmar Ratio (ann.) | {self._fmt_ratio(summary['calmar_ratio'])} |",
            f"| Max Drawdown | {summary['max_drawdown']:.2%} |",
            f"| Win Rate | {summary['win_rate']:.1%} |",
            f"| Profit Factor | {self._fmt_ratio(summary['profit_factor'])} |",
            f"| Expected Value | {self._fmt_usdt(summary['expected_value'])} |",
            "",
            "## Regime Performance",
        ]

        lines += self._regime_table(regime_perf)

        lines += ["", "## Direction Breakdown"]
        lines += self._direction_table(direction_perf)

        lines += ["", "## Model Contribution"]
        lines += self._model_table(model_contrib)

        lines += [
            "",
            "## Cost Analysis",
            f"| Cost Type | Amount | Share of Gross PnL |",
            f"|-----------|--------|---------------------|",
            f"| Funding fees | {df['funding_cost'].sum():.2f} USDT | {self._fmt_pct(funding['funding_share_pct'])} |",
            f"| Trading fees | {df['trading_fee'].sum():.2f} USDT | {self._fmt_pct(funding['fee_share_pct'])} |",
            f"| Slippage | {self._fmt_usdt(slippage['total_slippage_usdt'])} | {self._fmt_pct(slippage['slippage_pnl_share_pct'])} |",
        ]

        if candles_df is not None and not candles_df.empty:
            alpha_df = self.pnl_calc.btc_buy_hold_alpha(df, candles_df, self.initial_capital)
            if not alpha_df.empty:
                strategy_ret = (alpha_df["strategy_equity"].iloc[-1] - self.initial_capital) / self.initial_capital
                btc_ret = (alpha_df["btc_equity"].iloc[-1] - self.initial_capital) / self.initial_capital
                lines += [
                    "",
                    "## vs BTC Buy&Hold Benchmark",
                    f"| | Return |",
                    f"|---|---|",
                    f"| Strategy | {strategy_ret:.2%} |",
                    f"| BTC B&H | {btc_ret:.2%} |",
                    f"| **Alpha** | **{strategy_ret - btc_ret:.2%}** |",
                ]

        lines += [
            "",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Telegram helpers
    # ------------------------------------------------------------------

    def to_telegram_chunks(self, report: str) -> list[str]:
        """
        Split a Markdown report into Telegram-safe chunks (≤4096 chars).

        Splits on section headers (##) when possible to keep context.
        """
        if len(report) <= self.TELEGRAM_MAX_CHARS:
            return [report]

        chunks = []
        current_chunk = ""
        for line in report.split("\n"):
            candidate = current_chunk + line + "\n"
            if len(candidate) > self.TELEGRAM_MAX_CHARS:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                current_chunk = line + "\n"
            else:
                current_chunk = candidate

        if current_chunk.strip():
            chunks.append(current_chunk.rstrip())

        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_by_date(
        self, trades_df: pd.DataFrame, date: datetime, period: str
    ) -> pd.DataFrame:
        df = trades_df.copy()
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
        if period == "daily":
            mask = df["exit_time"].dt.normalize() == pd.Timestamp(date.date(), tz="UTC")
        else:
            mask = pd.Series([True] * len(df))
        return df[mask].reset_index(drop=True)

    def _filter_by_date_range(
        self,
        trades_df: pd.DataFrame,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        df = trades_df.copy()
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        mask = (df["exit_time"] >= start_ts) & (df["exit_time"] < end_ts)
        return df[mask].reset_index(drop=True)

    def _direction_table(self, direction_perf: pd.DataFrame) -> list[str]:
        lines = [
            "| Direction | Trades | Win Rate | Net PnL |",
            "|-----------|--------|----------|---------|",
        ]
        for _, row in direction_perf.iterrows():
            lines.append(
                f"| {row['direction_label']} "
                f"| {int(row['trade_count'])} "
                f"| {row['win_rate']:.1%} "
                f"| {row['total_net_pnl']:.2f} USDT |"
            )
        return lines

    def _regime_table(self, regime_perf: pd.DataFrame) -> list[str]:
        lines = [
            "| Regime | Trades | Win Rate | Net PnL |",
            "|--------|--------|----------|---------|",
        ]
        for _, row in regime_perf.iterrows():
            lines.append(
                f"| {row['regime']} "
                f"| {int(row['trade_count'])} "
                f"| {row['win_rate']:.1%} "
                f"| {row['total_net_pnl']:.2f} USDT |"
            )
        return lines

    def _model_table(self, model_contrib: pd.DataFrame) -> list[str]:
        lines = [
            "| Model | Avg Weight | Attributed PnL |",
            "|-------|-----------|----------------|",
        ]
        for _, row in model_contrib.iterrows():
            lines.append(
                f"| {row['model'].upper()} "
                f"| {row['avg_weight']:.1%} "
                f"| {row['total_attributed_pnl']:.2f} USDT |"
            )
        return lines

    @staticmethod
    def _fmt_ratio(val: float) -> str:
        if math.isnan(val):
            return "N/A"
        if math.isinf(val):
            return "∞"
        return f"{val:.2f}"

    @staticmethod
    def _fmt_usdt(val: float) -> str:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        return f"{val:.2f} USDT"

    @staticmethod
    def _fmt_pct(val: float) -> str:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        return f"{val:.1f}%"

    @staticmethod
    def _fmt_bps(val: float) -> str:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        return f"{val:.1f} bps"
