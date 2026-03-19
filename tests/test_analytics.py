"""
Tests for the Aegis analytics engine.

Covers:
- PnLCalculator: per-trade PnL, daily/weekly/monthly aggregation, equity curve, BTC B&H alpha
- PerformanceMetrics: Sharpe, Sortino, Calmar, win rate, profit factor, EV, streaks, heatmap, DOW
- Attribution: model contribution, regime/direction/time-of-day perf, funding cost, slippage
- ReportGenerator: daily/weekly/monthly Markdown reports, Telegram chunking
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from analytics.pnl_calculator import PnLCalculator, TradePnL
from analytics.performance_metrics import PerformanceMetrics
from analytics.attribution import Attribution
from analytics.report_generator import ReportGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2025, 1, 6, 0, 0, 0, tzinfo=timezone.utc)  # Monday


def _make_trades(n: int = 3) -> pd.DataFrame:
    """Return a small DataFrame of sample trades (without pre-computed PnL)."""
    rows = [
        {
            "trade_id": 1,
            "entry_time": BASE_TIME,
            "exit_time": BASE_TIME + timedelta(hours=2),
            "direction": 1,
            "entry_price": 40000.0,
            "exit_price": 40500.0,
            "size": 0.01,
            "leverage": 3.0,
            "funding_cost": 0.5,
            "regime": "TRENDING",
            "lgbm_weight": 0.5,
            "tra_weight": 0.3,
            "adarnn_weight": 0.2,
        },
        {
            "trade_id": 2,
            "entry_time": BASE_TIME + timedelta(hours=3),
            "exit_time": BASE_TIME + timedelta(hours=5),
            "direction": -1,
            "entry_price": 40500.0,
            "exit_price": 40200.0,
            "size": 0.01,
            "leverage": 3.0,
            "funding_cost": 0.2,
            "regime": "RANGING",
            "lgbm_weight": 0.4,
            "tra_weight": 0.4,
            "adarnn_weight": 0.2,
        },
        {
            "trade_id": 3,
            "entry_time": BASE_TIME + timedelta(hours=6),
            "exit_time": BASE_TIME + timedelta(hours=8),
            "direction": 1,
            "entry_price": 40200.0,
            "exit_price": 40100.0,
            "size": 0.01,
            "leverage": 3.0,
            "funding_cost": 0.1,
            "regime": "VOLATILE",
            "lgbm_weight": 0.33,
            "tra_weight": 0.33,
            "adarnn_weight": 0.34,
        },
    ]
    return pd.DataFrame(rows[:n])


def _make_candles(n: int = 48) -> pd.DataFrame:
    """Return simple ascending candle data for BTC benchmark tests."""
    rows = []
    price = 40000.0
    for i in range(n):
        rows.append(
            {
                "timestamp": BASE_TIME + timedelta(minutes=30 * i),
                "open": price,
                "high": price + 50,
                "low": price - 50,
                "close": price + i * 10,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# PnLCalculator
# ---------------------------------------------------------------------------


class TestPnLCalculator:
    calc = PnLCalculator()

    def test_single_trade_gross_pnl_long(self):
        """gross_pnl = (exit - entry) * size * leverage * direction"""
        t = self.calc.compute_trade_pnl(
            trade_id=1,
            entry_time=BASE_TIME,
            exit_time=BASE_TIME + timedelta(hours=1),
            direction=1,
            entry_price=40000,
            exit_price=41000,
            size=0.01,
            leverage=3,
        )
        assert t.gross_pnl == pytest.approx(1000 * 0.01 * 3 * 1, rel=1e-6)

    def test_single_trade_gross_pnl_short(self):
        t = self.calc.compute_trade_pnl(
            trade_id=2,
            entry_time=BASE_TIME,
            exit_time=BASE_TIME + timedelta(hours=1),
            direction=-1,
            entry_price=40000,
            exit_price=39000,
            size=0.01,
            leverage=3,
        )
        assert t.gross_pnl == pytest.approx((-1000) * 0.01 * 3 * (-1), rel=1e-6)

    def test_net_pnl_subtracts_costs(self):
        t = self.calc.compute_trade_pnl(
            trade_id=1,
            entry_time=BASE_TIME,
            exit_time=BASE_TIME + timedelta(hours=2),
            direction=1,
            entry_price=40000,
            exit_price=40500,
            size=0.01,
            leverage=3,
            funding_cost=0.5,
        )
        expected_gross = (40500 - 40000) * 0.01 * 3 * 1
        expected_fee = (40000 * 0.01 * 0.0004) + (40500 * 0.01 * 0.0004)
        assert t.gross_pnl == pytest.approx(expected_gross, rel=1e-6)
        assert t.net_pnl == pytest.approx(expected_gross - 0.5 - expected_fee, rel=1e-6)

    def test_net_pnl_pct_is_margin_relative(self):
        t = self.calc.compute_trade_pnl(
            trade_id=1,
            entry_time=BASE_TIME,
            exit_time=BASE_TIME + timedelta(hours=1),
            direction=1,
            entry_price=40000,
            exit_price=40500,
            size=0.01,
            leverage=3,
        )
        margin = 40000 * 0.01 / 3
        assert t.net_pnl_pct == pytest.approx(t.net_pnl / margin, rel=1e-6)

    def test_compute_trades_pnl_dataframe(self):
        trades = _make_trades()
        df = self.calc.compute_trades_pnl(trades)
        assert "gross_pnl" in df.columns
        assert "net_pnl" in df.columns
        assert "net_pnl_pct" in df.columns
        assert "trading_fee" in df.columns
        assert "hold_seconds" in df.columns
        assert len(df) == 3
        # First trade: long, price went up → positive gross
        assert df["gross_pnl"].iloc[0] > 0
        # Third trade: long, price went down → negative gross
        assert df["gross_pnl"].iloc[2] < 0

    def test_leverage_amplifies_pnl(self):
        """Doubling leverage should double gross PnL."""
        base_df = self.calc.compute_trades_pnl(_make_trades(1))
        trades2 = _make_trades(1)
        trades2["leverage"] = 6.0
        df2 = self.calc.compute_trades_pnl(trades2)
        assert df2["gross_pnl"].iloc[0] == pytest.approx(
            base_df["gross_pnl"].iloc[0] * 2, rel=1e-6
        )

    def test_daily_pnl_aggregation(self):
        trades = _make_trades()
        daily = self.calc.daily_pnl(trades)
        # All 3 trades exit on the same day
        assert len(daily) == 1
        assert daily["trade_count"].iloc[0] == 3

    def test_weekly_pnl_aggregation(self):
        trades = _make_trades()
        weekly = self.calc.weekly_pnl(trades)
        assert len(weekly) >= 1
        assert weekly["trade_count"].sum() == 3

    def test_monthly_pnl_aggregation(self):
        trades = _make_trades()
        monthly = self.calc.monthly_pnl(trades)
        assert len(monthly) == 1
        assert monthly["trade_count"].iloc[0] == 3

    def test_equity_curve_starts_at_initial_capital(self):
        eq = self.calc.equity_curve(_make_trades(), initial_capital=10_000)
        assert eq["equity"].iloc[0] == pytest.approx(10_000 + eq["net_pnl"].iloc[0], rel=1e-6)

    def test_equity_curve_is_cumulative(self):
        trades = _make_trades()
        eq = self.calc.equity_curve(trades, initial_capital=1000)
        df = self.calc.compute_trades_pnl(trades)
        expected_final = 1000 + df["net_pnl"].sum()
        assert eq["equity"].iloc[-1] == pytest.approx(expected_final, rel=1e-6)

    def test_btc_buy_hold_alpha_structure(self):
        candles = _make_candles()
        trades = _make_trades()
        result = self.calc.btc_buy_hold_alpha(trades, candles, initial_capital=1000)
        assert "strategy_equity" in result.columns
        assert "btc_equity" in result.columns
        assert "alpha" in result.columns
        assert len(result) > 0


# ---------------------------------------------------------------------------
# PerformanceMetrics
# ---------------------------------------------------------------------------


class TestPerformanceMetrics:
    perf = PerformanceMetrics()

    def _computed_df(self):
        calc = PnLCalculator()
        return calc.compute_trades_pnl(_make_trades())

    def test_win_rate_range(self):
        df = self._computed_df()
        wr = self.perf.win_rate(df["net_pnl"])
        assert 0.0 <= wr <= 1.0

    def test_win_rate_correct(self):
        # 2 wins, 1 loss in sample data
        df = self._computed_df()
        wr = self.perf.win_rate(df["net_pnl"])
        assert wr == pytest.approx(2 / 3, rel=1e-6)

    def test_profit_factor_positive(self):
        df = self._computed_df()
        pf = self.perf.profit_factor(df["net_pnl"])
        assert pf > 0

    def test_expected_value(self):
        df = self._computed_df()
        ev = self.perf.expected_value(df["net_pnl"])
        # EV should be close to mean net PnL
        assert ev == pytest.approx(df["net_pnl"].mean(), rel=0.05)

    def test_avg_hold_time_positive(self):
        df = self._computed_df()
        avg_h = self.perf.avg_hold_time(df["hold_seconds"])
        assert avg_h > 0

    def test_max_consecutive_wins(self):
        pnls = pd.Series([1, 2, -1, 3, 4, 5, -2])
        assert self.perf.max_consecutive_wins(pnls) == 3

    def test_max_consecutive_losses(self):
        pnls = pd.Series([1, -1, -2, -3, 1, -1])
        assert self.perf.max_consecutive_losses(pnls) == 3

    def test_sharpe_ratio_finite(self):
        returns = pd.Series([0.01, 0.02, -0.005, 0.015, -0.003])
        sharpe = self.perf.sharpe_ratio(returns)
        assert math.isfinite(sharpe)

    def test_sortino_ratio_greater_than_sharpe_when_few_losses(self):
        """Sortino >= Sharpe when downside vol < total vol."""
        returns = pd.Series([0.01, 0.02, 0.015, -0.001, 0.018])
        sharpe = self.perf.sharpe_ratio(returns)
        sortino = self.perf.sortino_ratio(returns)
        assert sortino >= sharpe

    def test_calmar_ratio_finite(self):
        returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
        calmar = self.perf.calmar_ratio(returns)
        assert math.isfinite(calmar)

    def test_hourly_heatmap_has_24_rows(self):
        df = self._computed_df()
        heatmap = self.perf.hourly_return_heatmap(df)
        assert len(heatmap) == 24
        assert set(heatmap["hour"]) == set(range(24))

    def test_day_of_week_has_7_rows(self):
        df = self._computed_df()
        dow = self.perf.day_of_week_distribution(df)
        assert len(dow) == 7
        assert "day_name" in dow.columns

    def test_full_summary_keys(self):
        df = self._computed_df()
        summary = self.perf.full_summary(df)
        required_keys = [
            "total_trades", "total_net_pnl", "win_rate", "profit_factor",
            "avg_win", "avg_loss", "expected_value", "avg_hold_time_h",
            "max_consecutive_wins", "max_consecutive_losses",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio", "max_drawdown",
        ]
        for k in required_keys:
            assert k in summary, f"Missing key: {k}"

    def test_empty_returns_nan(self):
        empty = pd.Series(dtype=float)
        assert math.isnan(self.perf.sharpe_ratio(empty))
        assert math.isnan(self.perf.win_rate(empty))


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


class TestAttribution:
    attr = Attribution()

    def test_model_contribution_sums_to_net_pnl(self):
        """Sum of attributed PnL across models should equal net_pnl per trade."""
        trades = _make_trades()
        detail = self.attr.model_contribution(trades)
        # Group by trade_id and sum attributed_pnl
        per_trade = detail.groupby("trade_id")["attributed_pnl"].sum()
        calc = PnLCalculator()
        df = calc.compute_trades_pnl(trades)
        for _, row in df.iterrows():
            assert per_trade[row["trade_id"]] == pytest.approx(row["net_pnl"], rel=1e-6)

    def test_model_contribution_weights_sum_to_one(self):
        trades = _make_trades()
        detail = self.attr.model_contribution(trades)
        per_trade_w = detail.groupby("trade_id")["weight"].sum()
        for w in per_trade_w:
            assert w == pytest.approx(1.0, abs=1e-9)

    def test_model_contribution_summary_has_all_models(self):
        trades = _make_trades()
        summary = self.attr.model_contribution_summary(trades)
        assert set(summary["model"]) == {"lgbm", "tra", "adarnn"}

    def test_regime_performance_covers_all_regimes(self):
        trades = _make_trades()
        result = self.attr.regime_performance(trades)
        assert set(result["regime"]) == {"TRENDING", "RANGING", "VOLATILE"}

    def test_regime_performance_win_rate_range(self):
        trades = _make_trades()
        result = self.attr.regime_performance(trades)
        for wr in result["win_rate"]:
            assert 0.0 <= wr <= 1.0

    def test_direction_performance_long_short(self):
        trades = _make_trades()
        result = self.attr.direction_performance(trades)
        assert "LONG" in result["direction_label"].values
        assert "SHORT" in result["direction_label"].values

    def test_direction_performance_trade_counts(self):
        trades = _make_trades()
        result = self.attr.direction_performance(trades)
        total = result["trade_count"].sum()
        assert total == len(trades)

    def test_time_of_day_has_24_rows(self):
        trades = _make_trades()
        result = self.attr.time_of_day_performance(trades)
        assert len(result) == 24

    def test_funding_cost_share_keys(self):
        trades = _make_trades()
        result = self.attr.funding_cost_share(trades)
        assert "total_gross_pnl" in result
        assert "total_funding_cost" in result
        assert "funding_share_pct" in result
        assert "total_trading_fee" in result
        assert "fee_share_pct" in result

    def test_funding_cost_share_values(self):
        trades = _make_trades()
        result = self.attr.funding_cost_share(trades)
        assert result["total_funding_cost"] == pytest.approx(0.8, abs=1e-6)
        assert result["funding_share_pct"] >= 0

    def test_slippage_impact_missing_columns(self):
        """Should return NaN values gracefully when slippage columns absent."""
        trades = _make_trades()
        result = self.attr.slippage_impact(trades)
        assert math.isnan(result["total_slippage_usdt"])

    def test_slippage_impact_with_data(self):
        trades = _make_trades(1)
        trades["intended_price"] = 40000.0
        trades["filled_price"] = 40010.0
        result = self.attr.slippage_impact(trades)
        assert result["avg_slippage_bps"] == pytest.approx(2.5, rel=1e-3)

    def test_full_attribution_keys(self):
        trades = _make_trades()
        result = self.attr.full_attribution(trades)
        assert set(result.keys()) == {
            "model_contribution",
            "regime_performance",
            "direction_performance",
            "time_of_day_performance",
            "funding_cost_share",
            "slippage_impact",
        }

    def test_works_with_raw_trades_no_pnl_columns(self):
        """Attribution must handle trades_df without pre-computed net_pnl."""
        raw = _make_trades()
        assert "net_pnl" not in raw.columns
        # Should not raise
        self.attr.model_contribution_summary(raw)
        self.attr.regime_performance(raw)
        self.attr.direction_performance(raw)


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class TestReportGenerator:
    rg = ReportGenerator(initial_capital=1000, environment="TESTNET")

    def test_daily_report_contains_key_sections(self):
        trades = _make_trades()
        report = self.rg.daily_report(trades, report_date=BASE_TIME)
        assert "Daily Report" in report
        assert "[TESTNET]" in report
        assert "Net PnL" in report
        assert "Win Rate" in report

    def test_daily_report_empty_trades(self):
        empty = pd.DataFrame(columns=_make_trades().columns)
        report = self.rg.daily_report(empty, report_date=BASE_TIME)
        assert "No trades" in report

    def test_weekly_report_contains_key_sections(self):
        trades = _make_trades()
        report = self.rg.weekly_report(trades, week_start=BASE_TIME)
        assert "Weekly Report" in report
        assert "Sharpe" in report
        assert "Regime" in report
        assert "Model Contribution" in report

    def test_weekly_report_empty_trades(self):
        empty = pd.DataFrame(columns=_make_trades().columns)
        report = self.rg.weekly_report(empty, week_start=BASE_TIME)
        assert "No trades" in report

    def test_monthly_report_contains_key_sections(self):
        trades = _make_trades()
        report = self.rg.monthly_report(trades, year=2025, month=1)
        assert "Monthly Report" in report
        assert "Calmar" in report
        assert "Cost Analysis" in report

    def test_monthly_report_with_btc_benchmark(self):
        trades = _make_trades()
        candles = _make_candles()
        report = self.rg.monthly_report(trades, year=2025, month=1, candles_df=candles)
        assert "BTC Buy" in report
        assert "Alpha" in report

    def test_telegram_chunks_under_4096_chars(self):
        trades = _make_trades()
        report = self.rg.monthly_report(trades, year=2025, month=1)
        chunks = self.rg.to_telegram_chunks(report)
        for chunk in chunks:
            assert len(chunk) <= ReportGenerator.TELEGRAM_MAX_CHARS

    def test_telegram_chunks_single_for_small_report(self):
        trades = _make_trades(1)
        report = self.rg.daily_report(trades, report_date=BASE_TIME)
        chunks = self.rg.to_telegram_chunks(report)
        assert len(chunks) == 1

    def test_telegram_chunks_multiple_for_large_report(self):
        """Construct a report larger than 4096 chars and verify splitting."""
        long_report = "# Title\n" + ("| col1 | col2 | col3 |\n|------|------|------|\n" * 120)
        chunks = self.rg.to_telegram_chunks(long_report)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= ReportGenerator.TELEGRAM_MAX_CHARS

    def test_mainnet_tag_in_report(self):
        rg_mainnet = ReportGenerator(environment="MAINNET")
        trades = _make_trades()
        report = rg_mainnet.daily_report(trades, report_date=BASE_TIME)
        assert "[MAINNET]" in report

    def test_report_generated_timestamp_present(self):
        trades = _make_trades()
        report = self.rg.daily_report(trades, report_date=BASE_TIME)
        assert "Generated:" in report
