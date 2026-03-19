"""Order manager — manages the lifecycle of orders from signal to fill.

Flow: signal → queue → execute → confirm → history
Handles unfilled orders, slippage tracking, and order history to DB.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from config.settings import settings
from execution.base import BaseExecutor

logger = logging.getLogger(__name__)

_UNFILLED_TIMEOUT_SECONDS = 300  # 5 minutes


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ManagedOrder:
    """Tracks a single order through its lifecycle."""

    internal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    side: str = ""
    amount: float = 0.0
    price: float | None = None          # None → market order
    order_type: str = "market"

    exchange_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    fill_price: float | None = None
    filled_amount: float = 0.0
    intended_price: float | None = None  # price at signal time (for slippage calc)
    slippage: float | None = None        # fill_price - intended_price (abs)
    error: str | None = None


class OrderManager:
    """Manages order queue and lifecycle for the execution engine.

    Usage:
        om = OrderManager(executor)
        om.submit_market_order("BTC/USDT:USDT", "buy", 0.001, intended_price=42000.0)
        om.process_queue()   # call periodically to confirm fills / cancel stale orders
    """

    def __init__(self, executor: BaseExecutor, storage=None) -> None:
        """
        executor: a BaseExecutor implementation (BinanceExecutor or PaperTrader)
        storage:  optional Storage instance for persisting order history to DB
        """
        self._executor = executor
        self._storage = storage
        self._queue: list[ManagedOrder] = []
        self._history: list[ManagedOrder] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        intended_price: float | None = None,
    ) -> ManagedOrder:
        """Add a market order to the queue and execute immediately."""
        order = ManagedOrder(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type="market",
            intended_price=intended_price,
        )
        self._queue.append(order)
        logger.info(
            "%s Queued market order %s: %s %s %.4f",
            settings.log_tag,
            order.internal_id[:8],
            side.upper(),
            symbol,
            amount,
        )
        self._execute_order(order)
        return order

    def submit_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        intended_price: float | None = None,
    ) -> ManagedOrder:
        """Add a limit order to the queue and execute immediately."""
        order = ManagedOrder(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            order_type="limit",
            intended_price=intended_price or price,
        )
        self._queue.append(order)
        logger.info(
            "%s Queued limit order %s: %s %s %.4f @ %.2f",
            settings.log_tag,
            order.internal_id[:8],
            side.upper(),
            symbol,
            amount,
            price,
        )
        self._execute_order(order)
        return order

    def process_queue(self) -> None:
        """Poll submitted orders; cancel stale ones and re-order at market.

        Should be called periodically (e.g. every 30 seconds).
        """
        still_open: list[ManagedOrder] = []
        for order in self._queue:
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED):
                self._archive(order)
                continue

            if order.status == OrderStatus.SUBMITTED and order.exchange_id:
                self._poll_fill(order)

            # Cancel limit orders that are unfilled after timeout
            if (
                order.status == OrderStatus.SUBMITTED
                and order.order_type == "limit"
                and order.submitted_at is not None
            ):
                age = (datetime.now(timezone.utc) - order.submitted_at).total_seconds()
                if age > _UNFILLED_TIMEOUT_SECONDS:
                    logger.warning(
                        "%s Order %s unfilled after %ds — cancelling and re-ordering at market.",
                        settings.log_tag,
                        order.internal_id[:8],
                        int(age),
                    )
                    self._cancel_and_reorder(order)
                    continue

            still_open.append(order)

        self._queue = still_open

    def get_history(self) -> list[ManagedOrder]:
        """Return all completed/archived orders."""
        return list(self._history)

    def get_open_orders(self) -> list[ManagedOrder]:
        """Return orders still in the queue."""
        return list(self._queue)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_order(self, order: ManagedOrder) -> None:
        """Submit the order to the exchange."""
        try:
            if order.order_type == "market":
                result = self._executor.create_market_order(
                    order.symbol, order.side, order.amount
                )
            else:
                result = self._executor.create_limit_order(
                    order.symbol, order.side, order.amount, order.price  # type: ignore[arg-type]
                )
            order.exchange_id = result.get("id")
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(timezone.utc)

            # Market orders may be immediately filled
            if result.get("status") in ("closed", "filled"):
                self._mark_filled(order, result)
        except Exception as exc:
            order.status = OrderStatus.FAILED
            order.error = str(exc)
            logger.error(
                "%s Order %s failed: %s", settings.log_tag, order.internal_id[:8], exc
            )
            self._archive(order)

    def _poll_fill(self, order: ManagedOrder) -> None:
        """Check exchange for fill status and update order."""
        try:
            status = self._executor.get_order_status(
                order.exchange_id,  # type: ignore[arg-type]
                order.symbol,
            )
            raw_status = status.get("status", "")
            if raw_status in ("closed", "filled"):
                self._mark_filled(order, status)
            elif raw_status == "canceled":
                order.status = OrderStatus.CANCELLED
                self._archive(order)
            elif raw_status == "partially_filled":
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_amount = float(status.get("filled", 0.0))
        except Exception as exc:
            logger.warning(
                "%s Could not poll order %s: %s",
                settings.log_tag,
                order.internal_id[:8],
                exc,
            )

    def _mark_filled(self, order: ManagedOrder, result: dict[str, Any]) -> None:
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now(timezone.utc)
        order.fill_price = float(result.get("average") or result.get("price") or 0)
        order.filled_amount = float(result.get("filled") or order.amount)

        if order.intended_price and order.fill_price:
            order.slippage = abs(order.fill_price - order.intended_price)
            slippage_pct = order.slippage / order.intended_price * 100
            logger.info(
                "%s Order %s filled @ %.4f (intended %.4f, slippage %.4f = %.3f%%)",
                settings.log_tag,
                order.internal_id[:8],
                order.fill_price,
                order.intended_price,
                order.slippage,
                slippage_pct,
            )
        else:
            logger.info(
                "%s Order %s filled @ %.4f",
                settings.log_tag,
                order.internal_id[:8],
                order.fill_price or 0,
            )
        self._archive(order)

    def _cancel_and_reorder(self, order: ManagedOrder) -> None:
        """Cancel a stale limit order and re-submit as market."""
        try:
            self._executor.cancel_order(order.exchange_id, order.symbol)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning(
                "%s Cancel failed for order %s: %s",
                settings.log_tag,
                order.internal_id[:8],
                exc,
            )

        order.status = OrderStatus.CANCELLED
        self._archive(order)

        # Re-order remaining amount at market
        remaining = order.amount - order.filled_amount
        if remaining > 0:
            logger.info(
                "%s Re-ordering %.4f %s at market after stale limit.",
                settings.log_tag,
                remaining,
                order.symbol,
            )
            self.submit_market_order(
                order.symbol,
                order.side,
                remaining,
                intended_price=order.intended_price,
            )

    def _archive(self, order: ManagedOrder) -> None:
        """Move order to history and persist to DB if storage is available."""
        self._history.append(order)
        self._persist_to_db(order)

    def _persist_to_db(self, order: ManagedOrder) -> None:
        """Persist order to storage if storage backend is configured."""
        if self._storage is None:
            return
        try:
            record = {
                "timestamp": (order.filled_at or order.submitted_at or datetime.now(timezone.utc)).isoformat(),
                "internal_id": order.internal_id,
                "exchange_id": order.exchange_id or "",
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "amount": order.amount,
                "filled_amount": order.filled_amount,
                "price": order.price,
                "fill_price": order.fill_price,
                "intended_price": order.intended_price,
                "slippage": order.slippage,
                "status": order.status.value,
                "error": order.error or "",
            }
            # Storage.save_order is expected to accept a dict
            if hasattr(self._storage, "save_order"):
                self._storage.save_order(record)
        except Exception as exc:
            logger.warning(
                "%s Failed to persist order %s to DB: %s",
                settings.log_tag,
                order.internal_id[:8],
                exc,
            )
