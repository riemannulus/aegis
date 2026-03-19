"""CCXT-based Binance Futures order executor.

Supports both Testnet and Mainnet via USE_TESTNET branching.
Inherits from BaseExecutor ABC.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import ccxt

from config.settings import settings
from execution.base import BaseExecutor

logger = logging.getLogger(__name__)

# Mainnet safety constants
_MAINNET_WARNING_COUNT = 3
_MAINNET_FIRST_ORDER_DELAY_S = 5
_MAINNET_MAX_SINGLE_ORDER_RATIO = 0.05   # 5% of balance per order
_MAINNET_DAILY_TRADE_LIMIT = 10

_RETRY_DELAYS = [1, 2, 4]  # exponential backoff seconds


def _retry_on_network_error(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) with up to 3 retries on NetworkError."""
    last_exc = None
    for delay in _RETRY_DELAYS:
        try:
            return fn(*args, **kwargs)
        except ccxt.NetworkError as exc:
            last_exc = exc
            logger.warning(
                "%s Network error, retrying in %ds: %s",
                settings.log_tag,
                delay,
                exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


class BinanceExecutor(BaseExecutor):
    """Executes Futures orders on Binance via CCXT.

    USE_TESTNET=True  → Binance Futures Testnet (sandbox mode)
    USE_TESTNET=False → Binance Futures Mainnet (safety guards active)
    """

    def __init__(self) -> None:
        self._exchange: ccxt.binance = settings.build_ccxt_exchange()
        self._use_testnet: bool = settings.USE_TESTNET
        self._first_order_sent = False
        self._daily_trade_count = 0
        self._daily_trade_date: str | None = None

        tag = settings.log_tag
        if settings.USE_TESTNET:
            logger.info("%s BinanceExecutor initialised (sandbox=True)", tag)
        else:
            for _ in range(_MAINNET_WARNING_COUNT):
                logger.warning(
                    "%s *** MAINNET MODE ACTIVE — real funds at risk ***", tag
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_mainnet_guards(self, amount: float) -> None:
        """Enforce mainnet safety constraints before order submission."""
        if settings.USE_TESTNET:
            return

        # 3x warning already logged at init; log again per order
        logger.warning(
            "%s Mainnet order about to be placed — double-check intent!", settings.log_tag
        )

        # 5-second delay before first order
        if not self._first_order_sent:
            logger.warning(
                "%s First mainnet order — sleeping %ds as safety delay.",
                settings.log_tag,
                _MAINNET_FIRST_ORDER_DELAY_S,
            )
            time.sleep(_MAINNET_FIRST_ORDER_DELAY_S)
            self._first_order_sent = True

        # Daily trade limit
        import datetime
        today = datetime.date.today().isoformat()
        if self._daily_trade_date != today:
            self._daily_trade_date = today
            self._daily_trade_count = 0
        if self._daily_trade_count >= _MAINNET_DAILY_TRADE_LIMIT:
            raise RuntimeError(
                f"{settings.log_tag} Daily trade limit ({_MAINNET_DAILY_TRADE_LIMIT}) reached. "
                "No further orders allowed today."
            )

        # 5% max single order size check
        balance = self.get_balance()
        total_usdt = balance.get("total", 0.0)
        if total_usdt > 0:
            # amount is in base asset units; get approximate USDT value
            ticker = _retry_on_network_error(
                self._exchange.fetch_ticker, settings.TRADING_SYMBOL
            )
            order_value_usdt = amount * ticker["last"]
            if order_value_usdt > total_usdt * _MAINNET_MAX_SINGLE_ORDER_RATIO:
                raise ValueError(
                    f"{settings.log_tag} Order size {order_value_usdt:.2f} USDT exceeds "
                    f"{_MAINNET_MAX_SINGLE_ORDER_RATIO*100:.0f}% of balance "
                    f"({total_usdt:.2f} USDT)."
                )

    def _increment_trade_count(self) -> None:
        if not settings.USE_TESTNET:
            self._daily_trade_count += 1

    # ------------------------------------------------------------------
    # BaseExecutor interface
    # ------------------------------------------------------------------

    def is_testnet(self) -> bool:
        return self._use_testnet

    def initialize_futures(self, symbol: str, leverage: int, margin_type: str) -> None:
        """Set leverage and margin type for a Futures symbol (called once at startup)."""
        binance_symbol = symbol.replace("/", "").replace(":USDT", "")
        try:
            _retry_on_network_error(
                self._exchange.fapiPrivate_post_leverage,
                {"symbol": binance_symbol, "leverage": leverage},
            )
            logger.info(
                "%s Leverage set to %dx for %s", settings.log_tag, leverage, binance_symbol
            )
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s Failed to set leverage: %s", settings.log_tag, exc
            )
            raise

        try:
            _retry_on_network_error(
                self._exchange.fapiPrivate_post_margintype,
                {"symbol": binance_symbol, "marginType": margin_type.upper()},
            )
            logger.info(
                "%s Margin type set to %s for %s",
                settings.log_tag,
                margin_type.upper(),
                binance_symbol,
            )
        except ccxt.ExchangeError as exc:
            # "No need to change margin type" is not a real error
            if "No need to change" in str(exc):
                logger.info(
                    "%s Margin type already %s for %s",
                    settings.log_tag,
                    margin_type.upper(),
                    binance_symbol,
                )
            else:
                logger.error(
                    "%s Failed to set margin type: %s", settings.log_tag, exc
                )
                raise

    def get_balance(self) -> dict[str, Any]:
        """Return Futures USDT balance: available, total (incl. unrealized PnL)."""
        try:
            raw = _retry_on_network_error(self._exchange.fetch_balance)
            usdt = raw.get("USDT", {})
            return {
                "available": usdt.get("free", 0.0),
                "total": usdt.get("total", 0.0),
                "unrealized_pnl": raw.get("info", {})
                .get("totalUnrealizedProfit", 0.0),
            }
        except ccxt.NetworkError as exc:
            logger.error("%s Network error fetching balance: %s", settings.log_tag, exc)
            raise
        except ccxt.ExchangeError as exc:
            logger.error("%s Exchange error fetching balance: %s", settings.log_tag, exc)
            raise

    def get_position(self, symbol: str) -> dict[str, Any]:
        """Return current open position for symbol."""
        try:
            positions = _retry_on_network_error(
                self._exchange.fetch_positions, [symbol]
            )
            for pos in positions:
                if pos["symbol"] == symbol and float(pos.get("contracts", 0) or 0) != 0:
                    return {
                        "side": pos.get("side"),
                        "size": float(pos.get("contracts", 0) or 0),
                        "entry_price": float(pos.get("entryPrice", 0) or 0),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0) or 0),
                        "liquidation_price": float(
                            pos.get("liquidationPrice", 0) or 0
                        ),
                        "leverage": float(pos.get("leverage", 1) or 1),
                        "margin_type": pos.get("marginType", "isolated"),
                    }
            # No open position
            return {
                "side": None,
                "size": 0.0,
                "entry_price": 0.0,
                "unrealized_pnl": 0.0,
                "liquidation_price": 0.0,
                "leverage": settings.LEVERAGE,
                "margin_type": settings.MARGIN_TYPE,
            }
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s Exchange error fetching position: %s", settings.log_tag, exc
            )
            raise

    def get_funding_rate(self, symbol: str | None = None) -> dict[str, Any]:
        """Return current funding rate for symbol."""
        sym = symbol or settings.TRADING_SYMBOL
        try:
            data = _retry_on_network_error(
                self._exchange.fetch_funding_rate, sym
            )
            return {
                "symbol": sym,
                "funding_rate": data.get("fundingRate", 0.0),
                "next_funding_time": data.get("nextFundingDatetime"),
            }
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s Failed to fetch funding rate: %s", settings.log_tag, exc
            )
            raise

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Submit a Futures market order with mainnet safety guards."""
        self._check_mainnet_guards(amount)
        try:
            order = _retry_on_network_error(
                self._exchange.create_market_order,
                symbol,
                side,
                amount,
                params=params or {},
            )
            self._increment_trade_count()
            logger.info(
                "%s Market order placed: %s %s %.4f @ market — id=%s",
                settings.log_tag,
                side.upper(),
                symbol,
                amount,
                order.get("id"),
            )
            return order
        except ccxt.InsufficientFunds as exc:
            logger.warning(
                "%s Insufficient funds for %.4f %s — attempting reduced size.",
                settings.log_tag,
                amount,
                symbol,
            )
            reduced = amount * 0.9
            order = _retry_on_network_error(
                self._exchange.create_market_order,
                symbol,
                side,
                reduced,
                params=params or {},
            )
            self._increment_trade_count()
            logger.info(
                "%s Reduced market order placed: %.4f %s — id=%s",
                settings.log_tag,
                reduced,
                symbol,
                order.get("id"),
            )
            return order
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s ExchangeError on market order: %s — notify telegram.", settings.log_tag, exc
            )
            raise

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Submit a Futures limit order."""
        self._check_mainnet_guards(amount)
        try:
            order = _retry_on_network_error(
                self._exchange.create_limit_order,
                symbol,
                side,
                amount,
                price,
                params=params or {},
            )
            self._increment_trade_count()
            logger.info(
                "%s Limit order placed: %s %s %.4f @ %.2f — id=%s",
                settings.log_tag,
                side.upper(),
                symbol,
                amount,
                price,
                order.get("id"),
            )
            return order
        except ccxt.InsufficientFunds as exc:
            logger.warning(
                "%s Insufficient funds for limit order %.4f %s @ %.2f: %s",
                settings.log_tag,
                amount,
                symbol,
                price,
                exc,
            )
            raise
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s ExchangeError on limit order: %s — notify telegram.", settings.log_tag, exc
            )
            raise

    def close_position(self, symbol: str, params: dict | None = None) -> dict[str, Any]:
        """Close the entire open position for symbol at market price."""
        position = self.get_position(symbol)
        size = position.get("size", 0.0)
        side = position.get("side")

        if size == 0.0 or side is None:
            logger.info("%s No open position to close for %s", settings.log_tag, symbol)
            return {"status": "no_position"}

        # To close a long → sell; to close a short → buy
        close_side = "sell" if side == "long" else "buy"
        logger.info(
            "%s Closing %s position: %s %.4f %s",
            settings.log_tag,
            side,
            close_side,
            size,
            symbol,
        )
        close_params = {"reduceOnly": True, **(params or {})}
        return self.create_market_order(symbol, close_side, size, params=close_params)

    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Cancel a pending order by ID."""
        try:
            result = _retry_on_network_error(
                self._exchange.cancel_order, order_id, symbol
            )
            logger.info(
                "%s Order %s cancelled for %s", settings.log_tag, order_id, symbol
            )
            return result
        except ccxt.OrderNotFound:
            logger.warning(
                "%s Order %s not found (already filled/cancelled?)", settings.log_tag, order_id
            )
            return {"id": order_id, "status": "not_found"}
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s Failed to cancel order %s: %s", settings.log_tag, order_id, exc
            )
            raise

    def get_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Return the current status of an order."""
        try:
            order = _retry_on_network_error(
                self._exchange.fetch_order, order_id, symbol
            )
            return {
                "id": order.get("id"),
                "status": order.get("status"),
                "filled": order.get("filled", 0.0),
                "remaining": order.get("remaining", 0.0),
                "average": order.get("average"),
                "side": order.get("side"),
                "amount": order.get("amount"),
            }
        except ccxt.OrderNotFound:
            return {"id": order_id, "status": "not_found"}
        except ccxt.ExchangeError as exc:
            logger.error(
                "%s Failed to fetch order %s: %s", settings.log_tag, order_id, exc
            )
            raise
