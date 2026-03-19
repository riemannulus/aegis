"""Tests for risk/risk_engine.py, position_limits.py, and drawdown_monitor.py."""

from __future__ import annotations

import pytest

from risk.position_limits import PositionLimits
from risk.drawdown_monitor import DrawdownMonitor, DrawdownAction
from risk.risk_engine import RiskEngine
from strategy.regime_detector import REGIME_PARAMS, REGIME_TRENDING, REGIME_VOLATILE


# ---------------------------------------------------------------------------
# PositionLimits tests
# ---------------------------------------------------------------------------

class TestPositionLimits:
    def setup_method(self):
        self.pl = PositionLimits()
        self.pl.reset_daily(opening_balance=10_000.0)

    def test_normal_order_passes(self):
        result = self.pl.check(order_usdt=500.0, account_balance=10_000.0)
        assert result.passed is True

    def test_position_exposure_exceeded(self):
        # MAX_POSITION_RATIO=0.3 → max 3000 USDT
        result = self.pl.check(order_usdt=4000.0, account_balance=10_000.0,
                               current_position_usdt=0.0)
        assert result.passed is False
        assert "포지션 한도" in result.reason

    def test_single_order_limit(self):
        # Single order limit = 10 % of balance = 1000 USDT
        result = self.pl.check(order_usdt=1500.0, account_balance=10_000.0)
        assert result.passed is False
        assert "단일 주문" in result.reason

    def test_daily_trade_count_exceeded(self):
        for _ in range(20):
            self.pl.record_trade(pnl=10.0)
        result = self.pl.check(order_usdt=100.0, account_balance=10_000.0)
        assert result.passed is False
        assert "일일 거래" in result.reason

    def test_daily_loss_limit_exceeded(self):
        # 5 % of 10000 = 500 USDT loss limit
        self.pl.record_trade(pnl=-600.0)
        result = self.pl.check(order_usdt=100.0, account_balance=10_000.0)
        assert result.passed is False
        assert "일일 손실" in result.reason

    def test_consecutive_loss_cooldown(self):
        for _ in range(5):
            self.pl.record_trade(pnl=-10.0)
        result = self.pl.check(order_usdt=100.0, account_balance=10_000.0)
        assert result.passed is False
        assert "쿨다운" in result.reason

    def test_cooldown_decrements_on_tick(self):
        for _ in range(5):
            self.pl.record_trade(pnl=-10.0)
        self.pl.tick_candle()
        # Cooldown should now be 0 (COOLDOWN_CANDLES=1)
        result = self.pl.check(order_usdt=100.0, account_balance=10_000.0)
        # After 1 tick the cooldown expires
        assert result.passed is True

    def test_reset_daily_clears_counters(self):
        for _ in range(15):
            self.pl.record_trade(pnl=-20.0)
        self.pl.reset_daily(opening_balance=10_000.0)
        result = self.pl.check(order_usdt=100.0, account_balance=10_000.0)
        assert result.passed is True


# ---------------------------------------------------------------------------
# DrawdownMonitor tests
# ---------------------------------------------------------------------------

class TestDrawdownMonitor:
    def test_no_drawdown_initially(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        status = dm.update(10_000.0)
        assert status.action == DrawdownAction.NONE
        assert status.drawdown_pct == pytest.approx(0.0)

    def test_warn_at_5_pct(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        status = dm.update(9_480.0)   # ~5.2 % DD
        assert status.action == DrawdownAction.WARN

    def test_reduce_at_8_pct(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        status = dm.update(9_150.0)   # ~8.5 % DD
        assert status.action == DrawdownAction.REDUCE_AND_BLOCK
        assert dm.is_new_position_blocked() is True

    def test_emergency_at_10_pct(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        status = dm.update(8_900.0)   # ~11 % DD
        assert status.action == DrawdownAction.EMERGENCY_CLOSE
        assert dm.is_halted() is True

    def test_hwm_updates_on_new_high(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        dm.update(11_000.0)
        assert dm._hwm == pytest.approx(11_000.0)

    def test_block_clears_after_new_hwm(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        dm.update(9_150.0)   # enter REDUCE zone
        assert dm.is_new_position_blocked()
        dm.update(10_100.0)  # new HWM — block should clear
        assert not dm.is_new_position_blocked()

    def test_halt_does_not_clear_automatically(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        dm.update(8_900.0)   # emergency
        dm.update(10_500.0)  # new HWM — but halted
        assert dm.is_halted() is True

    def test_manual_reset_clears_halt(self):
        dm = DrawdownMonitor(initial_equity=10_000.0)
        dm.update(8_900.0)
        dm.manual_reset_halt(new_equity=10_000.0)
        assert dm.is_halted() is False

    def test_callbacks_called(self):
        events = []
        dm = DrawdownMonitor(
            initial_equity=10_000.0,
            on_warn=lambda s: events.append("warn"),
            on_reduce=lambda s: events.append("reduce"),
            on_emergency=lambda s: events.append("emergency"),
        )
        dm.update(9_480.0)   # warn
        dm.update(9_150.0)   # reduce
        dm.update(8_900.0)   # emergency
        assert "warn" in events
        assert "reduce" in events
        assert "emergency" in events


# ---------------------------------------------------------------------------
# RiskEngine tests
# ---------------------------------------------------------------------------

class TestRiskEngine:
    def setup_method(self):
        self.re = RiskEngine()
        self.re.initialise(opening_balance=10_000.0)

    def test_stage1_passes_normal_order(self):
        result = self.re.check_pre_order(
            order_usdt=500.0, account_balance=10_000.0
        )
        assert result.passed is True

    def test_stage1_blocked_when_halted(self):
        # Force halt via drawdown monitor
        self.re.drawdown_monitor._halted = True
        result = self.re.check_pre_order(
            order_usdt=100.0, account_balance=10_000.0
        )
        assert result.passed is False

    def test_stage1_blocked_by_position_limit(self):
        result = self.re.check_pre_order(
            order_usdt=5000.0, account_balance=10_000.0,
            current_position_usdt=0.0
        )
        assert result.passed is False

    def test_stage2_stop_loss_triggered(self):
        self.re.set_regime_params(REGIME_PARAMS[REGIME_TRENDING])
        # TRENDING stop_loss = 3 %
        status = self.re.monitor_position(
            entry_price=100.0,
            current_price=96.5,    # -3.5 % → below 3 % SL
            position_side="LONG",
            position_size=0.1,
            leverage=3,
            account_equity=10_000.0,
        )
        assert status.stop_loss_triggered is True

    def test_stage2_take_profit_triggered(self):
        self.re.set_regime_params(REGIME_PARAMS[REGIME_TRENDING])
        # TRENDING take_profit = 6 %
        status = self.re.monitor_position(
            entry_price=100.0,
            current_price=107.0,   # +7 %
            position_side="LONG",
            position_size=0.1,
            leverage=3,
            account_equity=10_000.0,
        )
        assert status.take_profit_triggered is True

    def test_stage2_liquidation_close_90(self):
        status = self.re.monitor_position(
            entry_price=100.0,
            current_price=91.5,    # very close to liq
            position_side="LONG",
            position_size=0.1,
            leverage=3,
            account_equity=10_000.0,
            liquidation_price=90.0,
        )
        # 91.5 is 85 % of way from entry(100) to liq(90) → > 80% threshold
        assert status.liquidation_alert in ("WARN_80", "CLOSE_90")

    def test_stage2_no_trigger_normal(self):
        self.re.set_regime_params(REGIME_PARAMS[REGIME_VOLATILE])
        status = self.re.monitor_position(
            entry_price=100.0,
            current_price=100.5,   # +0.5 % — no triggers
            position_side="LONG",
            position_size=0.1,
            leverage=3,
            account_equity=10_000.0,
        )
        assert status.stop_loss_triggered is False
        assert status.take_profit_triggered is False
        assert status.emergency_close is False

    def test_drawdown_emergency_from_stage2(self):
        # Force equity to 89 % of HWM (>10% DD)
        self.re.drawdown_monitor._hwm = 10_000.0
        status = self.re.monitor_position(
            entry_price=100.0,
            current_price=100.0,
            position_side="LONG",
            position_size=0.1,
            leverage=3,
            account_equity=8_900.0,   # >10% DD
        )
        assert status.emergency_close is True

    def test_record_trade_result_tracks_loss(self):
        self.re.record_trade_result(-200.0)
        assert self.re.position_limits._daily_loss_usdt == pytest.approx(200.0)
        assert self.re.position_limits._consecutive_losses == 1
