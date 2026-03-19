"""Position manager: track Futures positions and compute target orders."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

MAX_LEVERAGE = 10


@dataclass
class PositionState:
    """Current Futures position snapshot."""
    side: str = "FLAT"            # "LONG" | "SHORT" | "FLAT"
    size: float = 0.0             # position size in base currency (BTC)
    entry_price: float = 0.0
    mark_price: float = 0.0
    leverage: int = settings.LEVERAGE
    liquidation_price: float = 0.0
    unrealized_pnl: float = 0.0
    accumulated_funding_cost: float = 0.0  # cumulative funding fees paid


@dataclass
class OrderIntent:
    """Describes what order(s) are needed to reach the target position."""
    action: str              # "OPEN_LONG" | "OPEN_SHORT" | "CLOSE_LONG" | "CLOSE_SHORT"
                             # | "FLIP_TO_LONG" | "FLIP_TO_SHORT" | "REDUCE" | "NONE"
    close_size: float = 0.0  # size to close first (for flips)
    open_side: Optional[str] = None   # "buy" (long) | "sell" (short)
    open_size: float = 0.0
    reason: str = ""


class PositionManager:
    """Track the current Futures position and generate order intents.

    Usage:
        pm = PositionManager()
        pm.update_from_exchange(side="LONG", size=0.01, entry_price=65000,
                                mark_price=66000, liquidation_price=55000)
        intent = pm.compute_order_intent(target_direction="SHORT", target_ratio=0.3,
                                         account_balance=1000.0)
    """

    def __init__(self) -> None:
        self.position = PositionState()
        self._leverage: int = settings.LEVERAGE

    # ------------------------------------------------------------------
    # State update
    # ------------------------------------------------------------------

    def update_from_exchange(
        self,
        side: str,
        size: float,
        entry_price: float,
        mark_price: float,
        liquidation_price: float = 0.0,
        unrealized_pnl: float = 0.0,
    ) -> None:
        """Sync position state from exchange data."""
        self.position.side = side.upper() if side else "FLAT"
        self.position.size = size
        self.position.entry_price = entry_price
        self.position.mark_price = mark_price
        self.position.liquidation_price = liquidation_price
        self.position.unrealized_pnl = unrealized_pnl
        self.position.leverage = self._leverage

    def update_mark_price(self, mark_price: float) -> None:
        """Update mark price and recalculate unrealized PnL."""
        self.position.mark_price = mark_price
        self.position.unrealized_pnl = self._calc_unrealized_pnl(mark_price)

    def add_funding_cost(self, cost: float) -> None:
        """Accumulate funding rate cost (positive = paid, negative = received)."""
        self.position.accumulated_funding_cost += cost
        logger.debug(
            "%s Funding cost +%.4f USDT, total=%.4f",
            settings.log_tag, cost, self.position.accumulated_funding_cost,
        )

    def set_leverage(self, leverage: int) -> None:
        if not (1 <= leverage <= MAX_LEVERAGE):
            raise ValueError(f"Leverage must be 1–{MAX_LEVERAGE}, got {leverage}")
        self._leverage = leverage
        self.position.leverage = leverage

    # ------------------------------------------------------------------
    # Order intent computation
    # ------------------------------------------------------------------

    def compute_order_intent(
        self,
        target_direction: str,   # "LONG" | "SHORT" | "FLAT"
        target_ratio: float,     # [0, 1] fraction of available margin to use
        account_balance: float,
        current_price: float = 0.0,
    ) -> OrderIntent:
        """Compare target vs current position and return required OrderIntent.

        Examples:
          target LONG 0.5, current FLAT  → OPEN_LONG
          target SHORT 0.3, current LONG 0.5 → close LONG then OPEN_SHORT
          target FLAT, current SHORT 0.3 → CLOSE_SHORT
        """
        target_direction = target_direction.upper()
        current_side = self.position.side

        # Compute target position size in BTC
        price = current_price or self.position.mark_price or self.position.entry_price
        target_size = 0.0
        if target_direction != "FLAT" and price > 0 and account_balance > 0:
            margin_usdt = account_balance * target_ratio * settings.MAX_POSITION_RATIO
            target_size = (margin_usdt * self._leverage) / price

        # ----- same direction or flat→flat --------------------------------
        if target_direction == current_side:
            return OrderIntent(action="NONE", reason="포지션 변경 불필요")

        # ----- flat target → close current --------------------------------
        if target_direction == "FLAT":
            close_action = (
                "CLOSE_LONG" if current_side == "LONG" else "CLOSE_SHORT"
            )
            return OrderIntent(
                action=close_action,
                close_size=self.position.size,
                reason="시그널 FLAT → 포지션 청산",
            )

        # ----- current is flat → open new ----------------------------------
        if current_side == "FLAT":
            open_action = "OPEN_LONG" if target_direction == "LONG" else "OPEN_SHORT"
            open_side_ccxt = "buy" if target_direction == "LONG" else "sell"
            return OrderIntent(
                action=open_action,
                open_side=open_side_ccxt,
                open_size=target_size,
                reason=f"FLAT → {target_direction} {target_size:.6f}",
            )

        # ----- direction flip: LONG→SHORT or SHORT→LONG --------------------
        flip_action = "FLIP_TO_LONG" if target_direction == "LONG" else "FLIP_TO_SHORT"
        open_side_ccxt = "buy" if target_direction == "LONG" else "sell"
        return OrderIntent(
            action=flip_action,
            close_size=self.position.size,
            open_side=open_side_ccxt,
            open_size=target_size,
            reason=f"{current_side} 청산 후 {target_direction} 진입",
        )

    # ------------------------------------------------------------------
    # Liquidation monitoring
    # ------------------------------------------------------------------

    def liquidation_proximity_pct(self) -> float:
        """Return how close mark price is to liquidation price (0–1).

        Returns 0 if no liquidation price is set.
        Returns 1.0 if mark == liq price.
        """
        liq = self.position.liquidation_price
        mark = self.position.mark_price
        entry = self.position.entry_price
        if liq <= 0 or mark <= 0 or entry <= 0:
            return 0.0
        distance_to_liq = abs(mark - liq)
        distance_entry_to_liq = abs(entry - liq)
        if distance_entry_to_liq < 1e-9:
            return 1.0
        return 1.0 - (distance_to_liq / distance_entry_to_liq)

    # ------------------------------------------------------------------
    # PnL helpers
    # ------------------------------------------------------------------

    def _calc_unrealized_pnl(self, mark_price: float) -> float:
        if self.position.side == "FLAT" or self.position.entry_price <= 0:
            return 0.0
        direction = 1 if self.position.side == "LONG" else -1
        return (
            self.position.size
            * (mark_price - self.position.entry_price)
            * self._leverage
            * direction
        )

    def average_entry_price(self) -> float:
        return self.position.entry_price

    def is_flat(self) -> bool:
        return self.position.side == "FLAT" or self.position.size == 0.0
