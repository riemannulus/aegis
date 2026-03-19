"""Decision logger: audit trail for every candle decision."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MarketSnapshot:
    price: float
    volume_24h: float
    funding_rate: float
    regime: str
    regime_confidence: float


@dataclass
class ModelPredictions:
    lgbm: float
    tra: float
    adarnn: float
    ensemble: float
    z_score: float
    tra_active_router: int
    tra_router_weights: List[float]


@dataclass
class SignalInfo:
    raw_position: float
    direction: str                   # "LONG" | "SHORT" | "FLAT"
    size_ratio: float
    cost_filter_passed: bool
    direction_filter_passed: bool
    min_hold_filter_passed: bool


@dataclass
class RiskCheckInfo:
    stage1_passed: bool
    stage1_detail: Dict[str, Any]
    drawdown_pct: float
    liquidation_distance_pct: float
    stop_loss_level: float
    take_profit_level: float
    stage2_notes: str = ""


@dataclass
class ExecutionInfo:
    order_id: str
    side: str
    amount: float
    intended_price: float
    filled_price: float
    slippage_bps: float
    fee_usdt: float
    latency_ms: float


@dataclass
class DecisionRecord:
    """Full audit record for a single candle decision."""
    timestamp: str                          # ISO-8601 UTC
    candle_id: str                          # e.g. "2024-01-15T08:30:00Z"

    market_snapshot: MarketSnapshot
    model_predictions: ModelPredictions
    top_features: List[Dict[str, Any]]      # [{"name": ..., "value": ...}, ...]

    signal: SignalInfo
    risk_check: RiskCheckInfo

    decision: str                           # EXECUTE | SKIP | REJECTED_BY_RISK | REDUCE | CLOSE
    decision_reason: str                    # human-readable Korean string

    execution: Optional[ExecutionInfo] = None


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class DecisionLogger:
    """Persist DecisionRecord to the decisions table every candle.

    Usage::

        logger_inst = DecisionLogger(storage)
        record = DecisionLogger.build_record(...)
        logger_inst.log(record)
    """

    DECISION_EXECUTE  = "EXECUTE"
    DECISION_SKIP     = "SKIP"
    DECISION_REJECTED = "REJECTED_BY_RISK"
    DECISION_REDUCE   = "REDUCE"
    DECISION_CLOSE    = "CLOSE"

    def __init__(self, storage=None) -> None:
        """
        Args:
            storage: optional data.storage.Storage instance; if None records
                     are only written to the Python logger.
        """
        self._storage = storage

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, record: DecisionRecord) -> None:
        """Persist a DecisionRecord to DB and Python logger."""
        try:
            record_dict = self._to_dict(record)
            if self._storage is not None:
                self._storage.save_decision(
                    timestamp=record.timestamp,
                    candle_id=record.candle_id,
                    decision=record.decision,
                    direction=record.signal.direction,
                    z_score=record.model_predictions.z_score,
                    regime=record.market_snapshot.regime,
                    reason=record.decision_reason,
                    full_record=json.dumps(record_dict, ensure_ascii=False),
                )
            logger.info(
                "%s [Decision] %s | %s | Z=%.2f | %s",
                settings.log_tag,
                record.decision,
                record.signal.direction,
                record.model_predictions.z_score,
                record.decision_reason,
            )
        except Exception as exc:
            logger.error("DecisionLogger.log failed: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_record(
        candle_id: str,
        market_snapshot: MarketSnapshot,
        model_predictions: ModelPredictions,
        top_features: List[Dict[str, Any]],
        signal: SignalInfo,
        risk_check: RiskCheckInfo,
        decision: str,
        decision_reason: str,
        execution: Optional[ExecutionInfo] = None,
    ) -> DecisionRecord:
        return DecisionRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            candle_id=candle_id,
            market_snapshot=market_snapshot,
            model_predictions=model_predictions,
            top_features=top_features,
            signal=signal,
            risk_check=risk_check,
            decision=decision,
            decision_reason=decision_reason,
            execution=execution,
        )

    @staticmethod
    def build_skip_reason(z_score: float, threshold: float) -> str:
        return (
            f"앙상블 Z={z_score:.2f} < threshold {threshold:.1f}, "
            f"시그널 강도 부족 관망"
        )

    @staticmethod
    def build_execute_reason(
        z_score: float, direction: str, regime: str, size_ratio: float
    ) -> str:
        return (
            f"앙상블 Z={z_score:.2f} > threshold {settings.MIN_SIGNAL_THRESHOLD:.1f}, "
            f"리스크 전부 통과, {regime} 레짐 {direction} 진입 (size={size_ratio:.2f})"
        )

    @staticmethod
    def build_rejected_reason(stage1_reason: str) -> str:
        return f"Stage 1 거부: {stage1_reason}"

    @staticmethod
    def build_cost_filter_reason(z_score: float) -> str:
        return f"앙상블 Z={z_score:.2f}, 거래비용 필터에 의해 시그널 무시"

    @staticmethod
    def build_direction_filter_reason(current_dir: str, target_dir: str, count: int, required: int) -> str:
        return (
            f"방향 전환 대기: {current_dir}→{target_dir} "
            f"({count}/{required}회 확인 중)"
        )

    @staticmethod
    def build_close_reason(trigger: str) -> str:
        reasons = {
            "stop_loss": "스탑로스 발동",
            "take_profit": "테이크프로핏 발동",
            "trailing_stop": "트레일링 스탑 발동",
            "drawdown": "최대 드로다운 초과 — 전체 청산",
            "liquidation_80": "청산가격 80% 접근 — 포지션 50% 축소",
            "liquidation_90": "청산가격 90% 접근 — 즉시 전체 청산",
            "signal_reverse": "시그널 반전 — 포지션 청산",
            "emergency": "긴급 청산",
            "manual": "수동 청산",
        }
        return reasons.get(trigger, f"포지션 청산: {trigger}")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(record: DecisionRecord) -> dict:
        d = asdict(record)
        # execution is Optional — keep as None if not present
        return d
