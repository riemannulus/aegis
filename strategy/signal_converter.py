"""Signal converter: model predictions → position signals."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import numpy as np

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    raw_prediction: float
    z_score: float
    raw_position: float          # clipped to [-1, 1]
    direction: str               # "LONG" | "SHORT" | "FLAT"
    size_ratio: float            # final position size [0, 1]
    cost_filter_passed: bool
    direction_filter_passed: bool
    min_hold_filter_passed: bool
    reason: str


class SignalConverter:
    """Convert ensemble model predictions into actionable position signals.

    Applies in order:
    1. Z-score normalisation
    2. Threshold gate (|z| < MIN_SIGNAL_THRESHOLD → FLAT)
    3. Trading-cost filter
    4. Direction-change confirmation filter (2 consecutive signals required)
    5. Minimum hold-time filter
    """

    SCALE_FACTOR = 0.5            # z × scale → raw position ratio
    FEE_RATE = 0.0004             # 0.04 % taker (Futures)
    LOOKBACK_WINDOW = 48          # candles for rolling std (24 h at 30 m)
    DIRECTION_CONFIRM = 2         # consecutive opposite signals before flipping
    MIN_HOLD_CANDLES = 2          # minimum candles to hold a position

    def __init__(self) -> None:
        self._pred_history: Deque[float] = deque(maxlen=self.LOOKBACK_WINDOW)
        self._current_direction: str = "FLAT"
        self._pending_flip_direction: Optional[str] = None
        self._pending_flip_count: int = 0
        self._hold_candles_remaining: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, prediction: float) -> SignalResult:
        """Convert a raw model prediction to a SignalResult."""
        self._pred_history.append(prediction)

        z_score = self._compute_zscore(prediction)
        threshold = settings.MIN_SIGNAL_THRESHOLD

        # ------ Step 1: threshold gate ------------------------------------
        if abs(z_score) < threshold:
            self._reset_flip_tracker()
            self._decrement_hold()
            return SignalResult(
                raw_prediction=prediction,
                z_score=z_score,
                raw_position=0.0,
                direction="FLAT",
                size_ratio=0.0,
                cost_filter_passed=True,
                direction_filter_passed=True,
                min_hold_filter_passed=True,
                reason=f"Z={z_score:.2f} below threshold {threshold:.1f}, 관망",
            )

        raw_position = float(np.clip(z_score * self.SCALE_FACTOR, -1.0, 1.0))
        candidate_dir = "LONG" if raw_position > 0 else "SHORT"

        # ------ Step 2: trading-cost filter --------------------------------
        expected_return = abs(raw_position) * abs(z_score) * 0.001  # approx
        if expected_return < 2 * self.FEE_RATE:
            self._reset_flip_tracker()
            self._decrement_hold()
            return SignalResult(
                raw_prediction=prediction,
                z_score=z_score,
                raw_position=raw_position,
                direction="FLAT",
                size_ratio=0.0,
                cost_filter_passed=False,
                direction_filter_passed=True,
                min_hold_filter_passed=True,
                reason=f"거래비용 필터: 기대수익({expected_return:.5f}) < 2×fee({2*self.FEE_RATE:.5f})",
            )

        # ------ Step 3: direction-change filter ----------------------------
        if self._current_direction not in ("FLAT", candidate_dir):
            # Opposite direction — require DIRECTION_CONFIRM consecutive signals
            if self._pending_flip_direction == candidate_dir:
                self._pending_flip_count += 1
            else:
                self._pending_flip_direction = candidate_dir
                self._pending_flip_count = 1

            if self._pending_flip_count < self.DIRECTION_CONFIRM:
                self._decrement_hold()
                return SignalResult(
                    raw_prediction=prediction,
                    z_score=z_score,
                    raw_position=raw_position,
                    direction=self._current_direction,
                    size_ratio=0.0,
                    cost_filter_passed=True,
                    direction_filter_passed=False,
                    min_hold_filter_passed=True,
                    reason=(
                        f"방향 전환 대기: {self._current_direction}→{candidate_dir} "
                        f"({self._pending_flip_count}/{self.DIRECTION_CONFIRM})"
                    ),
                )

        # ------ Step 4: minimum hold-time filter --------------------------
        if (self._hold_candles_remaining > 0
                and candidate_dir != self._current_direction
                and self._pending_flip_count < self.DIRECTION_CONFIRM):
            self._decrement_hold()
            return SignalResult(
                raw_prediction=prediction,
                z_score=z_score,
                raw_position=raw_position,
                direction=self._current_direction,
                size_ratio=0.0,
                cost_filter_passed=True,
                direction_filter_passed=True,
                min_hold_filter_passed=False,
                reason=f"최소 보유시간: {self._hold_candles_remaining}캔들 남음",
            )

        # ------ All filters passed — update state -------------------------
        self._reset_flip_tracker()
        prev_dir = self._current_direction
        self._current_direction = candidate_dir
        if prev_dir != candidate_dir:
            self._hold_candles_remaining = self.MIN_HOLD_CANDLES
        else:
            self._decrement_hold()

        size_ratio = abs(raw_position)
        return SignalResult(
            raw_prediction=prediction,
            z_score=z_score,
            raw_position=raw_position,
            direction=candidate_dir,
            size_ratio=size_ratio,
            cost_filter_passed=True,
            direction_filter_passed=True,
            min_hold_filter_passed=True,
            reason=f"Z={z_score:.2f} → {candidate_dir} size={size_ratio:.2f}",
        )

    def notify_position_closed(self) -> None:
        """Call when a position is externally closed to reset hold timer."""
        self._current_direction = "FLAT"
        self._hold_candles_remaining = 0
        self._reset_flip_tracker()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_zscore(self, prediction: float) -> float:
        if len(self._pred_history) < 2:
            return 0.0
        arr = np.array(self._pred_history)
        std = float(np.std(arr))
        if std < 1e-9:
            return 0.0
        mean = float(np.mean(arr))
        return (prediction - mean) / std

    def _reset_flip_tracker(self) -> None:
        self._pending_flip_direction = None
        self._pending_flip_count = 0

    def _decrement_hold(self) -> None:
        if self._hold_candles_remaining > 0:
            self._hold_candles_remaining -= 1
