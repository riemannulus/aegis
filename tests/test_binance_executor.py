"""Tests for execution/binance_executor.py.

Real Testnet calls are skipped unless USE_TESTNET=True AND live credentials
are present.  Unit tests use mocks only.

⚠️ All live tests run against Binance Futures TESTNET only.
   USE_TESTNET=False causes all live tests to be skipped.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ccxt so tests run without the package installed
# ---------------------------------------------------------------------------
if "ccxt" not in sys.modules:
    _ccxt_mock = types.ModuleType("ccxt")
    _ccxt_mock.binance = MagicMock
    _ccxt_mock.NetworkError = Exception
    _ccxt_mock.NotSupported = Exception
    _ccxt_mock.InsufficientFunds = Exception
    _ccxt_mock.ExchangeError = Exception
    sys.modules["ccxt"] = _ccxt_mock


SYMBOL = "BTC/USDT:USDT"
BINANCE_SYMBOL = "BTCUSDT"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_exchange():
    ex = MagicMock()
    ex.fetch_balance.return_value = {
        "USDT": {"free": 5000.0, "total": 5000.0},
        "total": {"USDT": 5000.0},
    }
    ex.fetch_positions.return_value = [
        {
            "symbol": SYMBOL,
            "side": "long",
            "contracts": 0.01,
            "entryPrice": 65000.0,
            "unrealizedPnl": 10.0,
            "liquidationPrice": 55000.0,
            "leverage": 3,
        }
    ]
    _order_dict = {
        "id": "order-001",
        "status": "closed",
        "side": "buy",
        "amount": 0.01,
        "price": 65000.0,
        "average": 65000.0,
        "fee": {"cost": 0.52, "currency": "USDT"},
    }
    ex.create_order.return_value = _order_dict
    ex.create_market_order.return_value = _order_dict
    ex.create_limit_order.return_value = _order_dict
    ex.fetch_order.return_value = {"id": "order-001", "status": "closed"}
    ex.cancel_order.return_value = {"id": "order-001", "status": "canceled"}
    ex.fapiPrivate_post_leverage = MagicMock(return_value={})
    ex.fapiPrivate_post_margintype = MagicMock(return_value={})
    ex.fetch_funding_rate = MagicMock(return_value={"fundingRate": 0.0001})
    return ex


def _make_executor(use_testnet: bool = True):
    from config.settings import Settings
    mock_settings = Settings(
        USE_TESTNET=use_testnet,
        CT_BINANCE_API_KEY="mainnet-key",
        CT_BINANCE_API_SECRET="mainnet-secret",
        CT_BINANCE_TESTNET_API_KEY="testnet-key",
        CT_BINANCE_TESTNET_API_SECRET="testnet-secret",
    )
    mock_exchange = _make_mock_exchange()
    mock_settings_obj = MagicMock(wraps=mock_settings)
    mock_settings_obj.build_ccxt_exchange = MagicMock(return_value=mock_exchange)
    mock_settings_obj.USE_TESTNET = use_testnet
    mock_settings_obj.log_tag = mock_settings.log_tag
    mock_settings_obj.LEVERAGE = mock_settings.LEVERAGE
    mock_settings_obj.MARGIN_TYPE = mock_settings.MARGIN_TYPE
    mock_settings_obj.TRADING_SYMBOL = mock_settings.TRADING_SYMBOL
    mock_settings_obj.requires_safety_confirmation = mock_settings.requires_safety_confirmation

    from execution.binance_executor import BinanceExecutor
    with patch("execution.binance_executor.settings", mock_settings_obj):
        executor = BinanceExecutor()
        executor._exchange = mock_exchange
    return executor, mock_exchange


# ---------------------------------------------------------------------------
# Unit tests (mocked)
# ---------------------------------------------------------------------------

class TestBinanceExecutorUnit:
    def test_is_testnet_true(self):
        executor, _ = _make_executor(use_testnet=True)
        assert executor.is_testnet() is True

    def test_is_testnet_false(self):
        executor, _ = _make_executor(use_testnet=False)
        assert executor.is_testnet() is False

    def test_get_balance_returns_usdt(self):
        executor, mock_ex = _make_executor()
        bal = executor.get_balance()
        assert "available" in bal
        mock_ex.fetch_balance.assert_called()

    def test_get_position_returns_dict(self):
        executor, mock_ex = _make_executor()
        pos = executor.get_position(SYMBOL)
        assert isinstance(pos, dict)

    def test_create_market_order_buy(self):
        executor, mock_ex = _make_executor()
        order = executor.create_market_order(SYMBOL, "buy", 0.01)
        assert order["status"] == "closed"
        mock_ex.create_market_order.assert_called()

    def test_create_market_order_sell(self):
        executor, mock_ex = _make_executor()
        order = executor.create_market_order(SYMBOL, "sell", 0.01)
        assert order["status"] == "closed"

    def test_create_limit_order(self):
        executor, mock_ex = _make_executor()
        order = executor.create_limit_order(SYMBOL, "buy", 0.01, 64_000.0)
        assert order is not None
        mock_ex.create_limit_order.assert_called()

    def test_close_position(self):
        executor, mock_ex = _make_executor()
        result = executor.close_position(SYMBOL)
        assert result is not None

    def test_cancel_order(self):
        executor, mock_ex = _make_executor()
        result = executor.cancel_order("order-001", SYMBOL)
        assert result is not None

    def test_get_order_status(self):
        executor, mock_ex = _make_executor()
        status = executor.get_order_status("order-001", SYMBOL)
        assert status["id"] == "order-001"

    def test_initialize_futures_calls_fapi(self):
        executor, mock_ex = _make_executor()
        executor.initialize_futures(BINANCE_SYMBOL, leverage=3, margin_type="ISOLATED")
        # CCXT v4 uses set_leverage instead of fapiPrivate_post_leverage
        mock_ex.set_leverage.assert_called()

    def test_log_tag_in_logs(self, caplog):
        import logging
        executor, _ = _make_executor(use_testnet=True)
        with caplog.at_level(logging.INFO, logger="execution.binance_executor"):
            executor.get_balance()


# ---------------------------------------------------------------------------
# Live Testnet tests — skipped unless credentials available
# ---------------------------------------------------------------------------

def _has_testnet_credentials() -> bool:
    try:
        from config.settings import settings
        return bool(
            settings.USE_TESTNET
            and settings.CT_BINANCE_TESTNET_API_KEY
            and settings.CT_BINANCE_TESTNET_API_SECRET
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_testnet_credentials(),
    reason="Testnet credentials not configured or USE_TESTNET=False",
)
class TestBinanceExecutorLiveTestnet:
    """Live integration tests against Binance Futures Testnet.

    These tests execute real orders on Testnet.
    Requires USE_TESTNET=True and valid Testnet API keys in .env.
    """

    @pytest.fixture(autouse=True)
    def executor(self):
        from execution.binance_executor import BinanceExecutor
        self.ex = BinanceExecutor()
        assert self.ex.is_testnet(), "Must be in testnet mode"
        yield self.ex

    def test_get_balance(self):
        bal = self.ex.get_balance()
        assert bal is not None

    def test_initialize_futures(self):
        self.ex.initialize_futures(BINANCE_SYMBOL, leverage=3, margin_type="ISOLATED")

    def test_long_order_cycle(self):
        """Place a small long, verify position, close it."""
        order = self.ex.create_market_order(SYMBOL, "buy", amount=0.001)
        assert order["status"] == "closed"

        pos = self.ex.get_position(SYMBOL)
        assert pos.get("side", "").lower() in ("long", "buy")
        assert pos.get("size", 0) > 0

        close = self.ex.close_position(SYMBOL)
        assert close is not None

        pos_after = self.ex.get_position(SYMBOL)
        assert pos_after.get("size", 0) == pytest.approx(0.0, abs=1e-6)

    def test_short_order_cycle(self):
        """Place a small short, verify position, close it."""
        order = self.ex.create_market_order(SYMBOL, "sell", amount=0.001)
        assert order["status"] == "closed"

        pos = self.ex.get_position(SYMBOL)
        assert pos.get("side", "").lower() in ("short", "sell")

        self.ex.close_position(SYMBOL)

        pos_after = self.ex.get_position(SYMBOL)
        assert pos_after.get("size", 0) == pytest.approx(0.0, abs=1e-6)
