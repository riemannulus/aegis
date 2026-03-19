"""Drawdown monitor: equity HWM tracking and level-based actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


class DrawdownAction(Enum):
    NONE = "NONE"
    WARN = "WARN"                    # 5 % — Telegram warning
    REDUCE_AND_BLOCK = "REDUCE"      # 8 % — halve positions, block new entries
    EMERGENCY_CLOSE = "EMERGENCY"    # 10 % — close all, halt system


@dataclass
class DrawdownStatus:
    equity: float
    hwm: float
    drawdown_pct: float              # 0 → 1
    action: DrawdownAction
    message: str


class DrawdownMonitor:
    """Track equity high-watermark and trigger actions at drawdown thresholds.

    Thresholds (from spec):
        5 %  → Telegram warning
        8 %  → Block new positions, reduce existing by 50 %
        10 % → Close all positions, pause system (manual restart required)
    """

    WARN_LEVEL    = 0.05
    REDUCE_LEVEL  = 0.08
    HALT_LEVEL    = 0.10

    def __init__(
        self,
        initial_equity: float = 0.0,
        on_warn: Optional[Callable[[DrawdownStatus], None]] = None,
        on_reduce: Optional[Callable[[DrawdownStatus], None]] = None,
        on_emergency: Optional[Callable[[DrawdownStatus], None]] = None,
    ) -> None:
        self._hwm: float = initial_equity
        self._halted: bool = False           # True after HALT — manual reset required
        self._new_positions_blocked: bool = False

        self._on_warn = on_warn
        self._on_reduce = on_reduce
        self._on_emergency = on_emergency

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, equity: float) -> DrawdownStatus:
        """Update equity and return current drawdown status.

        This should be called every candle (or more frequently) with the
        total account equity (balance + unrealized PnL).
        """
        # Update high-watermark
        if equity > self._hwm:
            self._hwm = equity
            if self._new_positions_blocked:
                logger.info(
                    "%s 신고점 회복 (%.2f USDT) — 포지션 블록 해제",
                    settings.log_tag, equity,
                )
                self._new_positions_blocked = False

        drawdown = self._calc_drawdown(equity)
        action = self._determine_action(drawdown)
        msg = self._build_message(equity, drawdown, action)

        status = DrawdownStatus(
            equity=equity,
            hwm=self._hwm,
            drawdown_pct=drawdown,
            action=action,
            message=msg,
        )

        self._fire_callbacks(action, status)
        return status

    def is_halted(self) -> bool:
        """Returns True after 10 % drawdown until manually reset."""
        return self._halted

    def is_new_position_blocked(self) -> bool:
        """Returns True at ≥ 8 % drawdown until new HWM is reached."""
        return self._halted or self._new_positions_blocked

    def manual_reset_halt(self, new_equity: float) -> None:
        """Operator manually resumes system after emergency halt."""
        logger.warning(
            "%s 드로다운 시스템 수동 재개 — equity=%.2f HWM=%.2f",
            settings.log_tag, new_equity, self._hwm,
        )
        self._halted = False
        self._new_positions_blocked = False
        self._hwm = new_equity

    def set_initial_equity(self, equity: float) -> None:
        if self._hwm == 0.0:
            self._hwm = equity

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calc_drawdown(self, equity: float) -> float:
        if self._hwm <= 0:
            return 0.0
        dd = (self._hwm - equity) / self._hwm
        return max(dd, 0.0)

    def _determine_action(self, drawdown: float) -> DrawdownAction:
        if drawdown >= self.HALT_LEVEL:
            return DrawdownAction.EMERGENCY_CLOSE
        if drawdown >= self.REDUCE_LEVEL:
            return DrawdownAction.REDUCE_AND_BLOCK
        if drawdown >= self.WARN_LEVEL:
            return DrawdownAction.WARN
        return DrawdownAction.NONE

    def _build_message(
        self, equity: float, drawdown: float, action: DrawdownAction
    ) -> str:
        tag = settings.log_tag
        base = (
            f"{tag} Drawdown={drawdown*100:.1f}% "
            f"(equity={equity:.2f} HWM={self._hwm:.2f})"
        )
        if action == DrawdownAction.EMERGENCY_CLOSE:
            return f"{base} → 🚨 긴급 청산 및 시스템 일시 정지"
        if action == DrawdownAction.REDUCE_AND_BLOCK:
            return f"{base} → ⚠️ 포지션 50% 축소, 신규 진입 차단"
        if action == DrawdownAction.WARN:
            return f"{base} → ⚠️ 드로다운 경고"
        return f"{base} → 정상"

    def _fire_callbacks(
        self, action: DrawdownAction, status: DrawdownStatus
    ) -> None:
        if action == DrawdownAction.EMERGENCY_CLOSE and not self._halted:
            self._halted = True
            self._new_positions_blocked = True
            logger.error(status.message)
            if self._on_emergency:
                self._on_emergency(status)

        elif action == DrawdownAction.REDUCE_AND_BLOCK:
            if not self._new_positions_blocked:
                self._new_positions_blocked = True
                logger.warning(status.message)
            if self._on_reduce:
                self._on_reduce(status)

        elif action == DrawdownAction.WARN:
            logger.warning(status.message)
            if self._on_warn:
                self._on_warn(status)
