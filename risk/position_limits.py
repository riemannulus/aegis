"""Position limit checks (Stage 1 pre-order validation)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.settings import settings

logger = logging.getLogger(__name__)

# Mainnet daily trade-count limit (more conservative)
MAINNET_MAX_DAILY_TRADES = 10
TESTNET_MAX_DAILY_TRADES = 20

# Single order max as fraction of account balance
MAX_SINGLE_ORDER_RATIO = 0.10
MAINNET_MAX_SINGLE_ORDER_RATIO = 0.05


@dataclass
class LimitCheckResult:
    passed: bool
    reason: str
    detail: dict


class PositionLimits:
    """Check whether a proposed order stays within all position limits.

    Checks performed (Stage 1 — before order submission):
      1. Total position exposure ≤ MAX_POSITION_RATIO × balance
      2. Single order size ≤ 10 % of balance (5 % on Mainnet)
      3. Daily trade count ≤ 20 (10 on Mainnet)
      4. Daily loss ≤ MAX_DAILY_LOSS_RATIO × opening balance
      5. Consecutive-loss cooldown (5 consecutive losses → 30-min pause)
    """

    CONSECUTIVE_LOSS_LIMIT = 5
    COOLDOWN_CANDLES = 1          # 30-min candles (= 30 min cooldown)

    def __init__(self) -> None:
        self._daily_trades: int = 0
        self._daily_loss_usdt: float = 0.0
        self._opening_balance: float = 0.0
        self._consecutive_losses: int = 0
        self._cooldown_remaining: int = 0
        self._current_position_usdt: float = 0.0

    # ------------------------------------------------------------------
    # Daily state management
    # ------------------------------------------------------------------

    def reset_daily(self, opening_balance: float) -> None:
        """Call at start of each trading day (00:00 UTC)."""
        self._daily_trades = 0
        self._daily_loss_usdt = 0.0
        self._opening_balance = opening_balance
        logger.info("%s Daily limits reset. Opening balance: %.2f USDT",
                    settings.log_tag, opening_balance)

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade result."""
        self._daily_trades += 1
        if pnl < 0:
            self._daily_loss_usdt += abs(pnl)
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.CONSECUTIVE_LOSS_LIMIT:
                self._cooldown_remaining = self.COOLDOWN_CANDLES
                logger.warning(
                    "%s %d consecutive losses — cooldown %d candles",
                    settings.log_tag, self._consecutive_losses, self.COOLDOWN_CANDLES,
                )
        else:
            self._consecutive_losses = 0

    def tick_candle(self) -> None:
        """Call once per candle to decrement cooldown counter."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

    def update_position_value(self, usdt_value: float) -> None:
        self._current_position_usdt = usdt_value

    # ------------------------------------------------------------------
    # Main check
    # ------------------------------------------------------------------

    def check(
        self,
        order_usdt: float,
        account_balance: float,
        current_position_usdt: float | None = None,
    ) -> LimitCheckResult:
        """Run all pre-order limit checks.

        Args:
            order_usdt: notional value of the proposed order in USDT.
            account_balance: current available USDT balance.
            current_position_usdt: total open position value; uses internal
                tracker if None.

        Returns:
            LimitCheckResult with passed=True if all checks pass.
        """
        if current_position_usdt is not None:
            self._current_position_usdt = current_position_usdt

        is_mainnet = not settings.USE_TESTNET

        # 1. Cooldown
        if self._cooldown_remaining > 0:
            return LimitCheckResult(
                passed=False,
                reason=f"연속 손실 쿨다운 {self._cooldown_remaining}캔들 남음",
                detail={"cooldown_remaining": self._cooldown_remaining},
            )

        # 2. Position exposure limit
        total_after = self._current_position_usdt + order_usdt
        max_position = account_balance * settings.MAX_POSITION_RATIO
        if total_after > max_position:
            return LimitCheckResult(
                passed=False,
                reason=(
                    f"포지션 한도 초과: {total_after:.2f} > "
                    f"{max_position:.2f} ({settings.MAX_POSITION_RATIO*100:.0f}%)"
                ),
                detail={
                    "total_after": total_after,
                    "max_position": max_position,
                    "ratio": settings.MAX_POSITION_RATIO,
                },
            )

        # 3. Single order size limit
        single_limit_ratio = (
            MAINNET_MAX_SINGLE_ORDER_RATIO if is_mainnet else MAX_SINGLE_ORDER_RATIO
        )
        single_limit = account_balance * single_limit_ratio
        if order_usdt > single_limit:
            return LimitCheckResult(
                passed=False,
                reason=f"단일 주문 한도 초과: {order_usdt:.2f} > {single_limit:.2f}",
                detail={"order_usdt": order_usdt, "single_limit": single_limit},
            )

        # 4. Daily trade count
        max_trades = MAINNET_MAX_DAILY_TRADES if is_mainnet else TESTNET_MAX_DAILY_TRADES
        if self._daily_trades >= max_trades:
            return LimitCheckResult(
                passed=False,
                reason=f"일일 거래 횟수 한도: {self._daily_trades}/{max_trades}",
                detail={"daily_trades": self._daily_trades, "max_trades": max_trades},
            )

        # 5. Daily loss limit
        if self._opening_balance > 0:
            loss_ratio = self._daily_loss_usdt / self._opening_balance
            if loss_ratio >= settings.MAX_DAILY_LOSS_RATIO:
                return LimitCheckResult(
                    passed=False,
                    reason=(
                        f"일일 손실 한도: {loss_ratio*100:.1f}%/"
                        f"{settings.MAX_DAILY_LOSS_RATIO*100:.0f}%"
                    ),
                    detail={
                        "daily_loss": self._daily_loss_usdt,
                        "opening_balance": self._opening_balance,
                        "loss_ratio": loss_ratio,
                    },
                )

        return LimitCheckResult(
            passed=True,
            reason="모든 포지션 한도 통과",
            detail={
                "daily_trades": self._daily_trades,
                "daily_loss_ratio": (
                    self._daily_loss_usdt / self._opening_balance
                    if self._opening_balance > 0 else 0.0
                ),
                "consecutive_losses": self._consecutive_losses,
            },
        )
