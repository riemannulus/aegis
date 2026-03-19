"""Regime detector: classify market regime from TRA router weights."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)

REGIME_TRENDING = "TRENDING"
REGIME_RANGING = "RANGING"
REGIME_VOLATILE = "VOLATILE"


@dataclass
class RegimeParams:
    """Per-regime strategy overrides."""
    max_position: float
    stop_loss_pct: float
    take_profit_pct: float


REGIME_PARAMS: Dict[str, RegimeParams] = {
    REGIME_TRENDING: RegimeParams(max_position=1.0, stop_loss_pct=0.03, take_profit_pct=0.06),
    REGIME_RANGING:  RegimeParams(max_position=0.5, stop_loss_pct=0.015, take_profit_pct=0.03),
    REGIME_VOLATILE: RegimeParams(max_position=0.3, stop_loss_pct=0.01, take_profit_pct=0.02),
}


@dataclass
class RegimeResult:
    regime: str                        # TRENDING | RANGING | VOLATILE
    confidence: float                  # dominant router weight
    router_weights: List[float]        # raw weights from TRA
    params: RegimeParams


class RegimeDetector:
    """Classify market regime from TRA router weights.

    The TRA model exposes K router weights (softmax probabilities) that sum
    to 1.  Each predictor is conceptually:
      - Index 0: momentum / trend-following predictor
      - Index 1: mean-reversion / ranging predictor
      - Index 2: defensive / low-signal predictor  (volatile / unclear regime)

    For K > 3, the remaining indices extend the defensive bucket.

    Classification rule:
      - TRENDING  if predictor[0] weight is dominant (≥ threshold)
      - RANGING   if predictor[1] weight is dominant
      - VOLATILE  otherwise (defensive predictors dominate, or tie)
    """

    DOMINANCE_THRESHOLD = 0.4   # weight must exceed this to "dominate"

    def __init__(self, num_predictors: int = 3) -> None:
        self.num_predictors = num_predictors
        self._last_regime: str = REGIME_VOLATILE

    def detect(self, router_weights: List[float]) -> RegimeResult:
        """Detect regime from TRA router weight vector.

        Args:
            router_weights: softmax weight vector of length K (sums to ~1).

        Returns:
            RegimeResult with regime, confidence and per-regime parameters.
        """
        if not router_weights:
            logger.warning("Empty router weights — defaulting to VOLATILE")
            return self._make_result(REGIME_VOLATILE, 0.0, router_weights)

        weights = list(router_weights)

        if len(weights) < 2:
            return self._make_result(REGIME_VOLATILE, weights[0] if weights else 0.0, weights)

        trend_w = weights[0]
        ranging_w = weights[1]
        # Remaining weights → defensive/volatile bucket
        defensive_w = sum(weights[2:]) if len(weights) > 2 else 0.0
        # Include predictor[1] in defensive if it is NOT ranging-dominant
        max_w = max(trend_w, ranging_w, defensive_w)

        if trend_w >= self.DOMINANCE_THRESHOLD and trend_w == max_w:
            regime = REGIME_TRENDING
            confidence = trend_w
        elif ranging_w >= self.DOMINANCE_THRESHOLD and ranging_w == max_w:
            regime = REGIME_RANGING
            confidence = ranging_w
        else:
            regime = REGIME_VOLATILE
            confidence = max_w

        self._last_regime = regime
        logger.debug(
            "Regime=%s confidence=%.3f weights=%s",
            regime, confidence, [f"{w:.3f}" for w in weights],
        )
        return self._make_result(regime, confidence, weights)

    def get_last_regime(self) -> str:
        return self._last_regime

    def get_params(self, regime: str) -> RegimeParams:
        return REGIME_PARAMS.get(regime, REGIME_PARAMS[REGIME_VOLATILE])

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _make_result(
        self, regime: str, confidence: float, weights: List[float]
    ) -> RegimeResult:
        return RegimeResult(
            regime=regime,
            confidence=confidence,
            router_weights=weights,
            params=REGIME_PARAMS[regime],
        )
