"""Tests for execution/paper_trader.py."""

from __future__ import annotations

import pytest

from execution.paper_trader import PaperTrader
from execution.base import BaseExecutor


SYMBOL = "BTCUSDT"


class TestPaperTraderInterface:
    def test_is_base_executor_subclass(self):
        assert issubclass(PaperTrader, BaseExecutor)

    def test_is_testnet_always_true(self):
        pt = PaperTrader(initial_balance=10_000.0)
        assert pt.is_testnet() is True

    def test_initial_balance(self):
        pt = PaperTrader(initial_balance=5_000.0)
        bal = pt.get_balance()
        assert bal["total"] == pytest.approx(5_000.0)
        assert bal["free"] == pytest.approx(5_000.0)

    def test_no_position_initially(self):
        pt = PaperTrader(initial_balance=10_000.0)
        pos = pt.get_position(SYMBOL)
        assert pos["side"] == "FLAT" or pos.get("size", 0) == 0

    def test_initialize_futures_sets_leverage(self):
        pt = PaperTrader(initial_balance=10_000.0)
        pt.initialize_futures(SYMBOL, leverage=5, margin_type="isolated")
        assert pt._leverage == 5


class TestPaperTraderOrders:
    def setup_method(self):
        self.pt = PaperTrader(initial_balance=10_000.0, leverage=3)
        self.pt._current_price = 65_000.0

    def test_create_market_long_order(self):
        order = self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        assert order["status"] == "closed"
        assert order["side"] == "buy"
        assert order["amount"] == pytest.approx(0.01)

    def test_create_market_short_order(self):
        order = self.pt.create_market_order(SYMBOL, side="sell", amount=0.01)
        assert order["status"] == "closed"
        assert order["side"] == "sell"

    def test_long_position_after_buy(self):
        self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        pos = self.pt.get_position(SYMBOL)
        assert pos["side"].lower() in ("long", "buy")
        assert pos["size"] == pytest.approx(0.01)

    def test_short_position_after_sell(self):
        self.pt.create_market_order(SYMBOL, side="sell", amount=0.01)
        pos = self.pt.get_position(SYMBOL)
        assert pos["side"].lower() in ("short", "sell")
        assert pos["size"] == pytest.approx(0.01)

    def test_close_long_position(self):
        self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        self.pt.close_position(SYMBOL)
        pos = self.pt.get_position(SYMBOL)
        assert pos.get("size", 0) == pytest.approx(0.0) or pos.get("side") == "FLAT"

    def test_fee_deducted_from_balance(self):
        initial = self.pt.get_balance()["free"]
        self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        after = self.pt.get_balance()["free"]
        assert after < initial

    def test_create_limit_order(self):
        order = self.pt.create_limit_order(SYMBOL, side="buy", amount=0.01, price=64_000.0)
        assert order is not None
        assert "id" in order

    def test_get_order_status(self):
        order = self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        status = self.pt.get_order_status(order["id"], SYMBOL)
        assert status["id"] == order["id"]

    def test_cancel_order(self):
        order = self.pt.create_limit_order(SYMBOL, side="buy", amount=0.01, price=50_000.0)
        result = self.pt.cancel_order(order["id"], SYMBOL)
        assert result is not None

    def test_liquidation_price_set_on_long(self):
        self.pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        pos = self.pt.get_position(SYMBOL)
        # liquidation_price should be below entry for longs
        assert pos.get("liquidation_price", 0) > 0
        assert pos["liquidation_price"] < self.pt._current_price


class TestPaperTraderPnL:
    def test_unrealized_pnl_increases_on_price_rise_long(self):
        pt = PaperTrader(initial_balance=10_000.0, leverage=3)
        pt._current_price = 60_000.0
        pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        pt._current_price = 62_000.0
        pt.update_mark_price(62_000.0)
        pos = pt.get_position(SYMBOL)
        assert pos.get("unrealized_pnl", 0) > 0

    def test_unrealized_pnl_increases_on_price_drop_short(self):
        pt = PaperTrader(initial_balance=10_000.0, leverage=3)
        pt._current_price = 60_000.0
        pt.create_market_order(SYMBOL, side="sell", amount=0.01)
        pt._current_price = 58_000.0
        pt.update_mark_price(58_000.0)
        pos = pt.get_position(SYMBOL)
        assert pos.get("unrealized_pnl", 0) > 0

    def test_trade_history_recorded(self):
        pt = PaperTrader(initial_balance=10_000.0, leverage=3)
        pt._current_price = 60_000.0
        pt.create_market_order(SYMBOL, side="buy", amount=0.01)
        pt._current_price = 61_000.0
        pt.close_position(SYMBOL)
        history = pt.get_trade_history()
        assert len(history) > 0
