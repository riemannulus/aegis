"""
Mainnet readiness tests for Aegis trading system.

ALL tests use mocks only — no actual Binance API calls are made.
These tests verify that the architecture correctly branches between
TESTNET and MAINNET without touching real funds.

Validates:
- Settings branching: correct API keys and tags per USE_TESTNET
- CCXT init branching: sandbox mode matches USE_TESTNET
- Both environments always use defaultType='future' (never 'spot')
- Mainnet safety guards active when USE_TESTNET=False
- Log/Telegram tag branching
- Risk engine conservative params on mainnet
- No hardcoded sandbox values (all from settings)
- Paper trader interface compatibility
"""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Mock ccxt at the module level so tests run without installing it.
# ---------------------------------------------------------------------------
_ccxt_mock = types.ModuleType("ccxt")
_ccxt_mock.binance = MagicMock  # class-level mock; instances created per test
_ccxt_mock.NetworkError = Exception
_ccxt_mock.InsufficientFunds = Exception
_ccxt_mock.ExchangeError = Exception
sys.modules.setdefault("ccxt", _ccxt_mock)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(use_testnet: bool, **kwargs):
    """Build a Settings instance with USE_TESTNET overridden."""
    from config.settings import Settings
    return Settings(
        USE_TESTNET=use_testnet,
        CT_BINANCE_API_KEY="mainnet-key",
        CT_BINANCE_API_SECRET="mainnet-secret",
        CT_BINANCE_TESTNET_API_KEY="testnet-key",
        CT_BINANCE_TESTNET_API_SECRET="testnet-secret",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Settings branching
# ---------------------------------------------------------------------------


class TestSettingsBranching:
    def test_testnet_uses_testnet_api_key(self):
        s = _make_settings(use_testnet=True)
        assert s.api_key == "testnet-key"
        assert s.api_secret == "testnet-secret"

    def test_mainnet_uses_mainnet_api_key(self):
        s = _make_settings(use_testnet=False)
        assert s.api_key == "mainnet-key"
        assert s.api_secret == "mainnet-secret"

    def test_testnet_log_tag(self):
        s = _make_settings(use_testnet=True)
        assert s.log_tag == "[TESTNET]"

    def test_mainnet_log_tag(self):
        s = _make_settings(use_testnet=False)
        assert s.log_tag == "[MAINNET]"

    def test_testnet_telegram_tag(self):
        s = _make_settings(use_testnet=True)
        assert s.telegram_tag == "[TESTNET]"

    def test_mainnet_telegram_tag(self):
        s = _make_settings(use_testnet=False)
        assert s.telegram_tag == "[MAINNET]"

    def test_testnet_sandbox_mode_true(self):
        s = _make_settings(use_testnet=True)
        assert s.sandbox_mode is True

    def test_mainnet_sandbox_mode_false(self):
        s = _make_settings(use_testnet=False)
        assert s.sandbox_mode is False

    def test_mainnet_requires_safety_confirmation(self):
        s = _make_settings(use_testnet=False)
        assert s.requires_safety_confirmation is True

    def test_testnet_no_safety_confirmation(self):
        s = _make_settings(use_testnet=True)
        assert s.requires_safety_confirmation is False

    def test_market_type_always_future(self):
        for use_testnet in [True, False]:
            s = _make_settings(use_testnet=use_testnet)
            assert s.MARKET_TYPE == "future", (
                f"MARKET_TYPE must be 'future' for USE_TESTNET={use_testnet}"
            )

    def test_no_hardcoded_sandbox_in_settings(self):
        """sandbox_mode must derive from USE_TESTNET, not a hardcoded value."""
        s_test = _make_settings(use_testnet=True)
        s_main = _make_settings(use_testnet=False)
        assert s_test.sandbox_mode != s_main.sandbox_mode


# ---------------------------------------------------------------------------
# CCXT exchange init branching
# ---------------------------------------------------------------------------


class TestCCXTInitBranching:
    def _build_exchange(self, use_testnet: bool):
        """Build exchange with mocked ccxt.binance via sys.modules."""
        s = _make_settings(use_testnet=use_testnet)
        mock_exchange = MagicMock()
        mock_binance_cls = MagicMock(return_value=mock_exchange)
        # Patch the binance constructor on the already-mocked ccxt module
        original_binance = sys.modules["ccxt"].binance
        sys.modules["ccxt"].binance = mock_binance_cls
        try:
            s.build_ccxt_exchange()
            init_kwargs = mock_binance_cls.call_args[0][0]
        finally:
            sys.modules["ccxt"].binance = original_binance
        return mock_exchange, init_kwargs, mock_exchange

    def test_testnet_sets_demo_mode(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=True)
        assert init_kwargs["options"]["demo"] is True

    def test_mainnet_does_not_set_demo_mode(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=False)
        assert "demo" not in init_kwargs["options"]

    def test_testnet_uses_testnet_api_key_in_ccxt(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=True)
        assert init_kwargs["apiKey"] == "testnet-key"
        assert init_kwargs["secret"] == "testnet-secret"

    def test_mainnet_uses_mainnet_api_key_in_ccxt(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=False)
        assert init_kwargs["apiKey"] == "mainnet-key"
        assert init_kwargs["secret"] == "mainnet-secret"

    def test_defaulttype_always_future_testnet(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=True)
        assert init_kwargs["options"]["defaultType"] == "future"

    def test_defaulttype_always_future_mainnet(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=False)
        assert init_kwargs["options"]["defaultType"] == "future"

    def test_rate_limit_enabled_testnet(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=True)
        assert init_kwargs["enableRateLimit"] is True

    def test_rate_limit_enabled_mainnet(self):
        _, init_kwargs, _ = self._build_exchange(use_testnet=False)
        assert init_kwargs["enableRateLimit"] is True


# ---------------------------------------------------------------------------
# BinanceExecutor safety guards
# ---------------------------------------------------------------------------


def _make_executor(use_testnet: bool):
    """Create BinanceExecutor with fully mocked settings and exchange."""
    from execution.binance_executor import BinanceExecutor

    mock_exchange = MagicMock()
    mock_settings = _make_settings(use_testnet=use_testnet)
    mock_settings_with_exchange = MagicMock(wraps=mock_settings)
    mock_settings_with_exchange.build_ccxt_exchange = MagicMock(return_value=mock_exchange)
    mock_settings_with_exchange.USE_TESTNET = use_testnet
    mock_settings_with_exchange.log_tag = mock_settings.log_tag

    with patch("execution.binance_executor.settings", mock_settings_with_exchange):
        executor = BinanceExecutor()
    return executor, mock_exchange, mock_settings_with_exchange


class TestBinanceExecutorSafetyGuards:
    def test_testnet_no_mainnet_warning_at_init(self, caplog):
        with caplog.at_level(logging.WARNING, logger="execution.binance_executor"):
            _make_executor(use_testnet=True)
        mainnet_warns = [r for r in caplog.records if "MAINNET" in r.message.upper()]
        assert len(mainnet_warns) == 0

    def test_mainnet_logs_warning_at_init(self, caplog):
        with caplog.at_level(logging.WARNING, logger="execution.binance_executor"):
            _make_executor(use_testnet=False)
        mainnet_warns = [r for r in caplog.records if "MAINNET" in r.message.upper()]
        assert len(mainnet_warns) >= 1

    def test_is_testnet_true_when_testnet(self):
        from execution.binance_executor import BinanceExecutor
        mock_exchange = MagicMock()
        mock_s = _make_settings(use_testnet=True)
        mock_s_obj = MagicMock(wraps=mock_s)
        mock_s_obj.build_ccxt_exchange = MagicMock(return_value=mock_exchange)
        mock_s_obj.USE_TESTNET = True
        mock_s_obj.log_tag = mock_s.log_tag
        with patch("execution.binance_executor.settings", mock_s_obj):
            executor = BinanceExecutor()
            result = executor.is_testnet()
        assert result is True

    def test_is_testnet_false_when_mainnet(self):
        from execution.binance_executor import BinanceExecutor
        mock_exchange = MagicMock()
        mock_s = _make_settings(use_testnet=False)
        mock_s_obj = MagicMock(wraps=mock_s)
        mock_s_obj.build_ccxt_exchange = MagicMock(return_value=mock_exchange)
        mock_s_obj.USE_TESTNET = False
        mock_s_obj.log_tag = mock_s.log_tag
        with patch("execution.binance_executor.settings", mock_s_obj):
            executor = BinanceExecutor()
            result = executor.is_testnet()
        assert result is False


# ---------------------------------------------------------------------------
# Log tag branching
# ---------------------------------------------------------------------------


class TestLogTagBranching:
    def test_testnet_log_tag_is_testnet(self):
        s = _make_settings(use_testnet=True)
        assert "[TESTNET]" in s.log_tag

    def test_mainnet_log_tag_is_mainnet(self):
        s = _make_settings(use_testnet=False)
        assert "[MAINNET]" in s.log_tag

    def test_log_tags_are_distinct(self):
        s_test = _make_settings(use_testnet=True)
        s_main = _make_settings(use_testnet=False)
        assert s_test.log_tag != s_main.log_tag

    def test_telegram_tags_are_distinct(self):
        s_test = _make_settings(use_testnet=True)
        s_main = _make_settings(use_testnet=False)
        assert s_test.telegram_tag != s_main.telegram_tag


# ---------------------------------------------------------------------------
# Risk engine conservative params
# ---------------------------------------------------------------------------


class TestRiskEngineConservativeParams:
    """Mainnet risk should be at least as conservative as testnet defaults."""

    def test_max_position_ratio_is_bounded(self):
        s = _make_settings(use_testnet=False)
        assert s.MAX_POSITION_RATIO <= 0.3

    def test_max_daily_loss_ratio_is_bounded(self):
        s = _make_settings(use_testnet=False)
        assert s.MAX_DAILY_LOSS_RATIO <= 0.05

    def test_max_drawdown_ratio_is_bounded(self):
        s = _make_settings(use_testnet=False)
        assert s.MAX_DRAWDOWN_RATIO <= 0.10

    def test_leverage_at_most_10x(self):
        s = _make_settings(use_testnet=False)
        assert s.LEVERAGE <= 10

    def test_margin_type_isolated_not_cross(self):
        """Isolated margin is safer — cross margin exposes full account."""
        for use_testnet in [True, False]:
            s = _make_settings(use_testnet=use_testnet)
            assert s.MARGIN_TYPE.lower() == "isolated", (
                f"MARGIN_TYPE must be 'isolated', got {s.MARGIN_TYPE!r}"
            )


# ---------------------------------------------------------------------------
# Paper trader interface compatibility
# ---------------------------------------------------------------------------


class TestPaperTraderInterface:
    """Verify PaperTrader implements the same BaseExecutor interface."""

    def test_paper_trader_is_base_executor(self):
        from execution.base import BaseExecutor
        from execution.paper_trader import PaperTrader
        assert issubclass(PaperTrader, BaseExecutor)

    def test_paper_trader_has_required_methods(self):
        from execution.paper_trader import PaperTrader
        required = [
            "get_balance",
            "get_position",
            "create_market_order",
            "create_limit_order",
            "close_position",
            "cancel_order",
            "get_order_status",
            "is_testnet",
            "initialize_futures",
        ]
        for method in required:
            assert hasattr(PaperTrader, method), f"PaperTrader missing method: {method}"

    def test_binance_executor_has_required_methods(self):
        from execution.binance_executor import BinanceExecutor
        required = [
            "get_balance",
            "get_position",
            "create_market_order",
            "create_limit_order",
            "close_position",
            "cancel_order",
            "get_order_status",
            "is_testnet",
            "initialize_futures",
        ]
        for method in required:
            assert hasattr(BinanceExecutor, method), f"BinanceExecutor missing method: {method}"

    def test_paper_trader_and_executor_share_interface(self):
        """Both executors must expose identical method names from BaseExecutor."""
        from execution.base import BaseExecutor
        from execution.binance_executor import BinanceExecutor
        from execution.paper_trader import PaperTrader
        import inspect

        abstract_methods = {
            name for name, member in inspect.getmembers(BaseExecutor)
            if getattr(member, "__isabstractmethod__", False)
        }
        for method in abstract_methods:
            assert hasattr(BinanceExecutor, method), f"BinanceExecutor missing: {method}"
            assert hasattr(PaperTrader, method), f"PaperTrader missing: {method}"


# ---------------------------------------------------------------------------
# No hardcoded sandbox values
# ---------------------------------------------------------------------------


class TestNoHardcodedSandboxValues:
    """Sandbox mode must be derived from USE_TESTNET, never hardcoded."""

    def test_settings_sandbox_follows_use_testnet(self):
        for use_testnet in [True, False]:
            s = _make_settings(use_testnet=use_testnet)
            assert s.sandbox_mode == use_testnet

    def test_settings_api_key_follows_use_testnet(self):
        s_test = _make_settings(use_testnet=True)
        s_main = _make_settings(use_testnet=False)
        assert s_test.api_key != s_main.api_key

    def test_build_ccxt_conditionally_sets_demo(self):
        """demo=True in options only for testnet, absent for mainnet."""
        original_binance = sys.modules["ccxt"].binance
        for use_testnet in [True, False]:
            s = _make_settings(use_testnet=use_testnet)
            mock_exchange = MagicMock()
            mock_binance_cls = MagicMock(return_value=mock_exchange)
            sys.modules["ccxt"].binance = mock_binance_cls
            try:
                s.build_ccxt_exchange()
                init_kwargs = mock_binance_cls.call_args[0][0]
            finally:
                sys.modules["ccxt"].binance = original_binance
            if use_testnet:
                assert init_kwargs["options"]["demo"] is True
            else:
                assert "demo" not in init_kwargs["options"]
