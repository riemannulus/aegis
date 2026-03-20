"""Paper trader — Futures simulation without exchange connection.

Implements the same BaseExecutor interface as BinanceExecutor.
Virtual fills at market price with realistic fees, funding costs,
leverage-adjusted PnL, and liquidation price simulation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from execution.base import BaseExecutor

logger = logging.getLogger(__name__)

# Fee structure (Binance Futures standard)
MAKER_FEE = 0.0002   # 0.02%
TAKER_FEE = 0.0004   # 0.04%

# Funding rate interval in seconds (8 hours)
FUNDING_INTERVAL_S = 8 * 3600

# Maintenance margin ratio for liquidation calc (simplified)
MAINTENANCE_MARGIN_RATIO = 0.004   # 0.4% for BTC futures


@dataclass
class PaperPosition:
    symbol: str
    side: str                # 'long' or 'short'
    size: float              # in base asset units
    entry_price: float
    leverage: int
    margin: float            # initial margin in USDT
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    accumulated_funding: float = 0.0
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PaperOrder:
    id: str
    symbol: str
    side: str
    amount: float
    price: float | None      # None = market
    order_type: str
    status: str
    fill_price: float
    fee: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _compute_liquidation_price(
    side: str,
    entry_price: float,
    leverage: int,
) -> float:
    """Simplified isolated-margin liquidation price estimate."""
    # Long: liq = entry * (1 - 1/leverage + maintenance_margin_ratio)
    # Short: liq = entry * (1 + 1/leverage - maintenance_margin_ratio)
    if side == "long":
        return entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN_RATIO)
    else:
        return entry_price * (1 + 1 / leverage - MAINTENANCE_MARGIN_RATIO)


class PaperTrader(BaseExecutor):
    """Simulates Binance Futures trading without real exchange connection.

    Uses the same interface as BinanceExecutor so the rest of the system
    cannot tell the difference.
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        leverage: int | None = None,
        funding_rate: float = 0.0001,  # default 0.01% per 8h
    ) -> None:
        self._balance_usdt = initial_balance
        self._leverage = leverage or settings.LEVERAGE
        self._funding_rate = funding_rate
        self._positions: dict[str, PaperPosition] = {}
        self._orders: list[PaperOrder] = []
        self._trades: list[dict] = []
        self._last_funding_ts: float = datetime.now(timezone.utc).timestamp()
        self._current_prices: dict[str, float] = {}

        logger.info(
            "%s PaperTrader initialised — balance=%.2f USDT, leverage=%dx",
            settings.log_tag,
            initial_balance,
            self._leverage,
        )

    # ------------------------------------------------------------------
    # Price feed (must be updated by the caller each candle)
    # ------------------------------------------------------------------

    def update_price(self, symbol: str, price: float) -> None:
        """Update the current market price for a symbol.

        Call this each time a new candle closes so PnL and funding
        cost simulations stay current.
        """
        self._current_prices[symbol] = price
        self._update_unrealized_pnl(symbol)
        self._maybe_apply_funding(symbol)
        self._check_liquidation(symbol)

    def _current_price(self, symbol: str) -> float:
        return self._current_prices.get(symbol, 0.0)

    # ------------------------------------------------------------------
    # BaseExecutor interface
    # ------------------------------------------------------------------

    def is_testnet(self) -> bool:
        return True  # paper trading is always "testnet-equivalent"

    def initialize_futures(self, symbol: str, leverage: int, margin_type: str) -> None:
        """Set leverage for simulation (margin_type is ignored — always isolated)."""
        self._leverage = leverage
        logger.info(
            "%s [PAPER] Futures initialised for %s: leverage=%dx margin=isolated",
            settings.log_tag,
            symbol,
            leverage,
        )

    def get_balance(self) -> dict[str, Any]:
        """Return simulated USDT balance."""
        total_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        return {
            "available": self._balance_usdt,
            "total": self._balance_usdt + total_pnl,
            "unrealized_pnl": total_pnl,
        }

    def get_position(self, symbol: str | None = None) -> dict[str, Any]:
        """Return current simulated position for symbol.

        If symbol is None, returns the first open position or a flat-position dict.
        """
        if symbol is None:
            if not self._positions:
                return {
                    "side": None,
                    "size": 0.0,
                    "entry_price": 0.0,
                    "unrealized_pnl": 0.0,
                    "liquidation_price": 0.0,
                    "leverage": self._leverage,
                    "margin_type": "isolated",
                }
            pos = next(iter(self._positions.values()))
        else:
            pos = self._positions.get(symbol)
        if pos is None:
            return {
                "side": None,
                "size": 0.0,
                "entry_price": 0.0,
                "unrealized_pnl": 0.0,
                "liquidation_price": 0.0,
                "leverage": self._leverage,
                "margin_type": "isolated",
            }
        return {
            "side": pos.side,
            "size": pos.size,
            "entry_price": pos.entry_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "liquidation_price": pos.liquidation_price,
            "leverage": pos.leverage,
            "margin_type": "isolated",
        }

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Simulate a market order fill at current price."""
        price = self._current_price(symbol)
        if price == 0.0:
            raise ValueError(
                f"[PAPER] No current price for {symbol}. Call update_price() first."
            )

        reduce_only = (params or {}).get("reduceOnly", False)
        fee = amount * price * TAKER_FEE
        order_id = str(uuid.uuid4())

        logger.info(
            "%s [PAPER] Market %s %s %.6f @ %.2f (fee=%.4f USDT)",
            settings.log_tag,
            side.upper(),
            symbol,
            amount,
            price,
            fee,
        )

        self._apply_fill(symbol, side, amount, price, fee, reduce_only=reduce_only)

        order = PaperOrder(
            id=order_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=None,
            order_type="market",
            status="closed",
            fill_price=price,
            fee=fee,
        )
        self._orders.append(order)
        return self._order_to_dict(order)

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Simulate a limit order as immediate fill at the requested price.

        In paper trading we assume best-case fill at the limit price,
        with maker fee applied.
        """
        fee = amount * price * MAKER_FEE
        order_id = str(uuid.uuid4())
        reduce_only = (params or {}).get("reduceOnly", False)

        logger.info(
            "%s [PAPER] Limit %s %s %.6f @ %.2f (fee=%.4f USDT)",
            settings.log_tag,
            side.upper(),
            symbol,
            amount,
            price,
            fee,
        )

        self._apply_fill(symbol, side, amount, price, fee, reduce_only=reduce_only)

        order = PaperOrder(
            id=order_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            order_type="limit",
            status="closed",
            fill_price=price,
            fee=fee,
        )
        self._orders.append(order)
        return self._order_to_dict(order)

    def close_position(self, symbol: str, params: dict | None = None) -> dict[str, Any]:
        """Close the entire simulated position for symbol at market price."""
        pos = self._positions.get(symbol)
        if pos is None:
            logger.info("%s [PAPER] No position to close for %s", settings.log_tag, symbol)
            return {"status": "no_position"}

        close_side = "sell" if pos.side == "long" else "buy"
        close_params = {"reduceOnly": True, **(params or {})}
        return self.create_market_order(symbol, close_side, pos.size, params=close_params)

    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Paper orders are filled instantly, so nothing to cancel."""
        logger.debug(
            "%s [PAPER] cancel_order called for %s (no-op in paper trading)", settings.log_tag, order_id
        )
        return {"id": order_id, "status": "canceled"}

    def get_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Look up a paper order by ID."""
        for order in reversed(self._orders):
            if order.id == order_id:
                return self._order_to_dict(order)
        return {"id": order_id, "status": "not_found"}

    # ------------------------------------------------------------------
    # Paper-trading-specific helpers
    # ------------------------------------------------------------------

    def get_order_history(self) -> list[dict[str, Any]]:
        """Return all simulated orders."""
        return [self._order_to_dict(o) for o in self._orders]

    def get_trade_history(self) -> list[dict[str, Any]]:
        """Return all completed trades (position closes)."""
        return list(self._trades)

    def set_funding_rate(self, rate: float) -> None:
        """Override the simulated funding rate (e.g. from live feed)."""
        self._funding_rate = rate

    # ------------------------------------------------------------------
    # Internal simulation logic
    # ------------------------------------------------------------------

    def _apply_fill(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        fee: float,
        reduce_only: bool = False,
    ) -> None:
        """Apply a fill to the paper account — open, close, or flip position."""
        existing = self._positions.get(symbol)

        # Determine if this closes or reduces the existing position
        if existing is not None:
            closes_long = existing.side == "long" and side == "sell"
            closes_short = existing.side == "short" and side == "buy"

            if closes_long or closes_short:
                self._close_or_reduce(symbol, existing, amount, price, fee)
                return
            elif reduce_only:
                # reduceOnly cannot open a new position
                return

        # Open or increase position
        self._open_or_increase(symbol, side, amount, price, fee)

    def _open_or_increase(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        fee: float,
    ) -> None:
        """Open a new position or add to an existing same-side position."""
        # Map buy/sell to long/short
        pos_side = "long" if side == "buy" else "short"
        margin = (amount * price) / self._leverage

        if margin + fee > self._balance_usdt:
            raise ValueError(
                f"[PAPER] Insufficient funds: need {margin + fee:.2f} USDT, "
                f"have {self._balance_usdt:.2f} USDT"
            )

        self._balance_usdt -= (margin + fee)

        existing = self._positions.get(symbol)
        if existing is not None and existing.side == pos_side:
            # Average in
            total_size = existing.size + amount
            avg_price = (existing.entry_price * existing.size + price * amount) / total_size
            existing.size = total_size
            existing.entry_price = avg_price
            existing.margin += margin
            existing.liquidation_price = _compute_liquidation_price(pos_side, avg_price, self._leverage)
        else:
            liq_price = _compute_liquidation_price(pos_side, price, self._leverage)
            self._positions[symbol] = PaperPosition(
                symbol=symbol,
                side=pos_side,
                size=amount,
                entry_price=price,
                leverage=self._leverage,
                margin=margin,
                liquidation_price=liq_price,
            )

        logger.debug(
            "%s [PAPER] Opened/increased %s %s %.6f @ %.2f — margin=%.2f USDT",
            settings.log_tag,
            pos_side,
            symbol,
            amount,
            price,
            margin,
        )

    def _close_or_reduce(
        self,
        symbol: str,
        pos: PaperPosition,
        amount: float,
        price: float,
        fee: float,
    ) -> None:
        """Close or partially reduce an existing position."""
        close_amount = min(amount, pos.size)

        if pos.side == "long":
            pnl = (price - pos.entry_price) * close_amount * self._leverage
        else:
            pnl = (pos.entry_price - price) * close_amount * self._leverage

        # Return margin proportionally
        margin_returned = pos.margin * (close_amount / pos.size)
        pos.margin -= margin_returned
        self._balance_usdt += margin_returned + pnl - fee

        logger.info(
            "%s [PAPER] Closed %s position %.6f @ %.2f — PnL=%.4f USDT (net of fee=%.4f)",
            settings.log_tag,
            pos.side,
            close_amount,
            price,
            pnl,
            fee,
        )

        self._trades.append({
            "symbol": symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": price,
            "size": close_amount,
            "pnl": round(pnl - fee, 6),
            "fee": round(fee, 6),
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })

        if close_amount >= pos.size:
            del self._positions[symbol]
        else:
            pos.size -= close_amount

    def _update_unrealized_pnl(self, symbol: str) -> None:
        """Recalculate unrealized PnL at current price."""
        pos = self._positions.get(symbol)
        if pos is None:
            return
        price = self._current_price(symbol)
        if pos.side == "long":
            pos.unrealized_pnl = (price - pos.entry_price) * pos.size * pos.leverage
        else:
            pos.unrealized_pnl = (pos.entry_price - price) * pos.size * pos.leverage

    def _maybe_apply_funding(self, symbol: str) -> None:
        """Apply funding cost if an 8-hour interval has elapsed."""
        now_ts = datetime.now(timezone.utc).timestamp()
        elapsed = now_ts - self._last_funding_ts
        if elapsed < FUNDING_INTERVAL_S:
            return

        pos = self._positions.get(symbol)
        if pos is None:
            self._last_funding_ts = now_ts
            return

        price = self._current_price(symbol)
        notional = pos.size * price
        funding_cost = notional * self._funding_rate

        # Longs pay funding, shorts receive (simplified one-way)
        if pos.side == "long":
            self._balance_usdt -= funding_cost
            pos.accumulated_funding += funding_cost
        else:
            self._balance_usdt += funding_cost
            pos.accumulated_funding -= funding_cost

        logger.debug(
            "%s [PAPER] Funding applied for %s %s: %.6f USDT (rate=%.6f)",
            settings.log_tag,
            pos.side,
            symbol,
            funding_cost,
            self._funding_rate,
        )
        self._last_funding_ts = now_ts

    def _check_liquidation(self, symbol: str) -> None:
        """Check if current price triggers liquidation."""
        pos = self._positions.get(symbol)
        if pos is None:
            return
        price = self._current_price(symbol)
        liquidated = False

        if pos.side == "long" and price <= pos.liquidation_price:
            liquidated = True
        elif pos.side == "short" and price >= pos.liquidation_price:
            liquidated = True

        if liquidated:
            logger.warning(
                "%s [PAPER] LIQUIDATION: %s %s at %.2f (liq price=%.2f) — position wiped.",
                settings.log_tag,
                pos.side,
                symbol,
                price,
                pos.liquidation_price,
            )
            # Lose remaining margin
            self._balance_usdt -= pos.margin
            if self._balance_usdt < 0:
                self._balance_usdt = 0.0
            del self._positions[symbol]

    @staticmethod
    def _order_to_dict(order: PaperOrder) -> dict[str, Any]:
        return {
            "id": order.id,
            "symbol": order.symbol,
            "side": order.side,
            "amount": order.amount,
            "price": order.price,
            "average": order.fill_price,
            "filled": order.amount,
            "remaining": 0.0,
            "status": order.status,
            "fee": order.fee,
            "timestamp": order.timestamp.isoformat(),
            "order_type": order.order_type,
        }
