"""2-stage risk management engine for Aegis Futures trading."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings
from risk.position_limits import LimitCheckResult, PositionLimits
from risk.drawdown_monitor import DrawdownMonitor, DrawdownAction
from strategy.regime_detector import RegimeParams, REGIME_VOLATILE, REGIME_PARAMS

logger = logging.getLogger(__name__)

# Liquidation proximity thresholds (Futures-specific)
LIQ_WARN_PROXIMITY  = 0.80   # 80 % of way from entry to liq → 50 % reduce
LIQ_CLOSE_PROXIMITY = 0.90   # 90 % → full emergency close

# Funding-rate risk threshold (absolute %)
FUNDING_ALERT_THRESHOLD = 0.001   # 0.1 %

# Trailing stop parameters
TRAILING_STOP_ACTIVATE_PCT = 0.02   # activate when unrealized PnL ≥ 2 %
TRAILING_STOP_TRAIL_PCT    = 0.01   # close if drops 1 % from peak


@dataclass
class Stage1Result:
    passed: bool
    limit_check: LimitCheckResult
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class Stage2Status:
    """Real-time monitoring snapshot during position hold."""
    stop_loss_triggered: bool = False
    take_profit_triggered: bool = False
    trailing_stop_triggered: bool = False
    drawdown_action: str = "NONE"
    liquidation_alert: str = "NONE"      # "NONE" | "WARN_80" | "CLOSE_90"
    funding_rate_warning: bool = False
    emergency_close: bool = False
    message: str = ""


class RiskEngine:
    """Two-stage risk management.

    Stage 1 (pre-order): called before submitting any order.
    Stage 2 (real-time): called every candle while a position is open.
    """

    def __init__(self) -> None:
        self.position_limits = PositionLimits()
        self.drawdown_monitor = DrawdownMonitor(
            on_warn=self._on_drawdown_warn,
            on_reduce=self._on_drawdown_reduce,
            on_emergency=self._on_drawdown_emergency,
        )
        self._regime_params: RegimeParams = REGIME_PARAMS[REGIME_VOLATILE]
        self._peak_unrealized_pnl: float = 0.0   # for trailing stop
        self._trailing_active: bool = False
        self._emergency_close_requested: bool = False

        # External callbacks (set by orchestrator)
        self.on_emergency_close = None     # callable()
        self.on_reduce_position = None     # callable(fraction: float)
        self.on_telegram_alert = None      # callable(msg: str)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_regime_params(self, params: RegimeParams) -> None:
        self._regime_params = params

    def initialise(self, opening_balance: float) -> None:
        self.position_limits.reset_daily(opening_balance)
        self.drawdown_monitor.set_initial_equity(opening_balance)
        self._emergency_close_requested = False

    # ------------------------------------------------------------------
    # Stage 1: Pre-order checks
    # ------------------------------------------------------------------

    def check_pre_order(
        self,
        order_usdt: float,
        account_balance: float,
        current_position_usdt: float = 0.0,
    ) -> Stage1Result:
        """Run Stage 1 checks before order submission.

        Returns Stage1Result.passed=True only if all limits are satisfied.
        """
        if self.drawdown_monitor.is_halted():
            return Stage1Result(
                passed=False,
                limit_check=LimitCheckResult(
                    passed=False,
                    reason="드로다운 긴급 정지 상태 — 수동 재개 필요",
                    detail={},
                ),
                reason="시스템 긴급 정지 상태",
            )

        if self.drawdown_monitor.is_new_position_blocked():
            return Stage1Result(
                passed=False,
                limit_check=LimitCheckResult(
                    passed=False,
                    reason="드로다운 8% 이상 — 신규 포지션 차단",
                    detail={},
                ),
                reason="신규 포지션 차단 중",
            )

        lc = self.position_limits.check(order_usdt, account_balance, current_position_usdt)
        if not lc.passed:
            return Stage1Result(passed=False, limit_check=lc, reason=lc.reason)

        return Stage1Result(
            passed=True,
            limit_check=lc,
            reason="Stage 1 전체 통과",
            detail=lc.detail,
        )

    # ------------------------------------------------------------------
    # Stage 2: Real-time monitoring
    # ------------------------------------------------------------------

    def monitor_position(
        self,
        entry_price: float,
        current_price: float,
        position_side: str,         # "LONG" | "SHORT"
        position_size: float,
        leverage: int,
        account_equity: float,
        liquidation_price: float = 0.0,
        funding_rate: float = 0.0,
    ) -> Stage2Status:
        """Monitor an open position and return Stage2Status.

        Should be called every candle while a position is held.
        """
        status = Stage2Status()

        if position_side == "FLAT" or position_size == 0:
            return status

        direction = 1 if position_side == "LONG" else -1
        pnl_pct = direction * (current_price - entry_price) / entry_price

        # --- Drawdown monitor -------------------------------------------
        dd_status = self.drawdown_monitor.update(account_equity)
        status.drawdown_action = dd_status.action.value
        if dd_status.action == DrawdownAction.EMERGENCY_CLOSE:
            status.emergency_close = True
            status.message = dd_status.message
            return status

        # --- Stop-loss (regime-based) ------------------------------------
        sl = self._regime_params.stop_loss_pct
        if pnl_pct <= -sl:
            status.stop_loss_triggered = True
            status.message = (
                f"스탑로스 발동: PnL={pnl_pct*100:.2f}% ≤ -{sl*100:.1f}%"
            )
            logger.warning("%s %s", settings.log_tag, status.message)
            return status

        # --- Take-profit -------------------------------------------------
        tp = self._regime_params.take_profit_pct
        if pnl_pct >= tp:
            status.take_profit_triggered = True
            status.message = (
                f"테이크프로핏 발동: PnL={pnl_pct*100:.2f}% ≥ {tp*100:.1f}%"
            )
            logger.info("%s %s", settings.log_tag, status.message)
            return status

        # --- Trailing stop -----------------------------------------------
        unrealized_pnl_usdt = position_size * (current_price - entry_price) * direction
        if unrealized_pnl_usdt > 0:
            if unrealized_pnl_usdt > self._peak_unrealized_pnl:
                self._peak_unrealized_pnl = unrealized_pnl_usdt
            if pnl_pct >= TRAILING_STOP_ACTIVATE_PCT:
                self._trailing_active = True
        if self._trailing_active and self._peak_unrealized_pnl > 0:
            drop_pct = (
                (self._peak_unrealized_pnl - unrealized_pnl_usdt)
                / self._peak_unrealized_pnl
            )
            if drop_pct >= TRAILING_STOP_TRAIL_PCT:
                status.trailing_stop_triggered = True
                status.message = (
                    f"트레일링 스탑: 고점 대비 {drop_pct*100:.2f}% 하락"
                )
                self._reset_trailing()
                return status

        # --- Liquidation proximity (Futures-specific) --------------------
        if liquidation_price > 0:
            dist_entry_liq = abs(entry_price - liquidation_price)
            dist_current_liq = abs(current_price - liquidation_price)
            if dist_entry_liq > 0:
                proximity = 1.0 - dist_current_liq / dist_entry_liq
                if proximity >= LIQ_CLOSE_PROXIMITY:
                    status.liquidation_alert = "CLOSE_90"
                    status.emergency_close = True
                    msg = (
                        f"청산가격 90% 접근 — 즉시 전체 청산! "
                        f"현재가={current_price:.2f}, 청산가={liquidation_price:.2f}"
                    )
                    status.message = msg
                    logger.error("%s %s", settings.log_tag, msg)
                    self._send_alert(f"🚨 {settings.telegram_tag} {msg}")
                    return status
                elif proximity >= LIQ_WARN_PROXIMITY:
                    status.liquidation_alert = "WARN_80"
                    msg = (
                        f"청산가격 80% 접근 — 포지션 50% 축소! "
                        f"현재가={current_price:.2f}, 청산가={liquidation_price:.2f}"
                    )
                    logger.warning("%s %s", settings.log_tag, msg)
                    self._send_alert(f"⚠️ {settings.telegram_tag} {msg}")
                    if self.on_reduce_position:
                        self.on_reduce_position(0.5)

        # --- Funding rate risk -------------------------------------------
        if abs(funding_rate) >= FUNDING_ALERT_THRESHOLD:
            status.funding_rate_warning = True
            logger.info(
                "%s 펀딩레이트 경고: %.4f%% (포지션 방향 확인 필요)",
                settings.log_tag, funding_rate * 100,
            )

        return status

    # ------------------------------------------------------------------
    # Candle tick (position limits)
    # ------------------------------------------------------------------

    def tick_candle(self) -> None:
        """Call every candle for cooldown/counter management."""
        self.position_limits.tick_candle()

    def record_trade_result(self, pnl: float) -> None:
        """Record completed trade outcome for daily tracking."""
        self.position_limits.record_trade(pnl)
        if pnl < 0:
            self.position_limits._daily_loss_usdt  # updated inside record_trade

    def reset_trailing_stop(self) -> None:
        self._reset_trailing()

    # ------------------------------------------------------------------
    # Drawdown callbacks
    # ------------------------------------------------------------------

    def _on_drawdown_warn(self, status) -> None:
        self._send_alert(f"⚠️ {settings.telegram_tag} {status.message}")

    def _on_drawdown_reduce(self, status) -> None:
        self._send_alert(f"⚠️ {settings.telegram_tag} {status.message}")
        if self.on_reduce_position:
            self.on_reduce_position(0.5)

    def _on_drawdown_emergency(self, status) -> None:
        self._send_alert(f"🚨 {settings.telegram_tag} {status.message}")
        if self.on_emergency_close:
            self.on_emergency_close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_trailing(self) -> None:
        self._peak_unrealized_pnl = 0.0
        self._trailing_active = False

    def _send_alert(self, msg: str) -> None:
        if self.on_telegram_alert:
            try:
                self.on_telegram_alert(msg)
            except Exception as exc:
                logger.error("Telegram alert failed: %s", exc)
