"""Tests for strategy/decision_logger.py."""

from __future__ import annotations

import json

import pytest

from strategy.decision_logger import (
    DecisionLogger,
    DecisionRecord,
    MarketSnapshot,
    ModelPredictions,
    SignalInfo,
    RiskCheckInfo,
    ExecutionInfo,
)


def _make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        price=65000.0,
        volume_24h=1_500_000.0,
        funding_rate=0.0001,
        regime="TRENDING",
        regime_confidence=0.72,
    )


def _make_predictions(z: float = 1.9) -> ModelPredictions:
    return ModelPredictions(
        lgbm=0.0012,
        tra=0.0015,
        adarnn=0.0011,
        ensemble=0.0013,
        z_score=z,
        tra_active_router=0,
        tra_router_weights=[0.72, 0.18, 0.10],
    )


def _make_signal(direction: str = "LONG", size: float = 0.6) -> SignalInfo:
    return SignalInfo(
        raw_position=size,
        direction=direction,
        size_ratio=size,
        cost_filter_passed=True,
        direction_filter_passed=True,
        min_hold_filter_passed=True,
    )


def _make_risk(passed: bool = True) -> RiskCheckInfo:
    return RiskCheckInfo(
        stage1_passed=passed,
        stage1_detail={"daily_trades": 3},
        drawdown_pct=0.02,
        liquidation_distance_pct=0.30,
        stop_loss_level=0.03,
        take_profit_level=0.06,
    )


def _make_execution() -> ExecutionInfo:
    return ExecutionInfo(
        order_id="TEST-001",
        side="buy",
        amount=0.01,
        intended_price=65000.0,
        filled_price=65002.0,
        slippage_bps=0.31,
        fee_usdt=0.52,
        latency_ms=120.0,
    )


# ---------------------------------------------------------------------------

class TestDecisionRecord:
    def test_build_record_creates_valid_record(self):
        record = DecisionLogger.build_record(
            candle_id="2024-01-15T08:30:00Z",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(),
            top_features=[{"name": "return_1h", "value": 0.012}],
            signal=_make_signal(),
            risk_check=_make_risk(),
            decision=DecisionLogger.DECISION_EXECUTE,
            decision_reason="테스트 이유",
            execution=_make_execution(),
        )
        assert isinstance(record, DecisionRecord)
        assert record.decision == "EXECUTE"
        assert record.execution is not None
        assert record.timestamp != ""

    def test_build_record_without_execution(self):
        record = DecisionLogger.build_record(
            candle_id="2024-01-15T09:00:00Z",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(z=0.4),
            top_features=[],
            signal=_make_signal(direction="FLAT", size=0.0),
            risk_check=_make_risk(),
            decision=DecisionLogger.DECISION_SKIP,
            decision_reason="Z 낮음",
        )
        assert record.decision == "SKIP"
        assert record.execution is None


class TestDecisionLoggerPersistence:
    def test_log_without_storage_does_not_raise(self):
        dl = DecisionLogger(storage=None)
        record = DecisionLogger.build_record(
            candle_id="2024-01-15T09:30:00Z",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(),
            top_features=[],
            signal=_make_signal(),
            risk_check=_make_risk(),
            decision=DecisionLogger.DECISION_EXECUTE,
            decision_reason="통과",
            execution=_make_execution(),
        )
        dl.log(record)  # should not raise

    def test_log_with_mock_storage(self):
        saved = {}

        class MockStorage:
            def save_decision(self, **kwargs):
                saved.update(kwargs)

        dl = DecisionLogger(storage=MockStorage())
        record = DecisionLogger.build_record(
            candle_id="2024-01-15T10:00:00Z",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(),
            top_features=[],
            signal=_make_signal(),
            risk_check=_make_risk(),
            decision=DecisionLogger.DECISION_EXECUTE,
            decision_reason="통과",
        )
        dl.log(record)
        assert saved["decision"] == "EXECUTE"
        assert saved["direction"] == "LONG"
        assert "full_record" in saved
        parsed = json.loads(saved["full_record"])
        assert parsed["decision"] == "EXECUTE"

    def test_log_rejected_by_risk(self):
        saved = {}

        class MockStorage:
            def save_decision(self, **kwargs):
                saved.update(kwargs)

        dl = DecisionLogger(storage=MockStorage())
        record = DecisionLogger.build_record(
            candle_id="2024-01-15T11:00:00Z",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(z=2.1),
            top_features=[],
            signal=_make_signal(),
            risk_check=_make_risk(passed=False),
            decision=DecisionLogger.DECISION_REJECTED,
            decision_reason=DecisionLogger.build_rejected_reason("일일 손실 한도 4.8%/5% 근접"),
        )
        dl.log(record)
        assert saved["decision"] == "REJECTED_BY_RISK"
        assert "Stage 1 거부" in saved["reason"]


class TestReasonBuilders:
    def test_skip_reason(self):
        reason = DecisionLogger.build_skip_reason(z_score=0.4, threshold=1.0)
        assert "0.40" in reason
        assert "관망" in reason

    def test_execute_reason(self):
        reason = DecisionLogger.build_execute_reason(
            z_score=1.9, direction="LONG", regime="TRENDING", size_ratio=0.6
        )
        assert "1.90" in reason
        assert "LONG" in reason
        assert "TRENDING" in reason

    def test_rejected_reason(self):
        reason = DecisionLogger.build_rejected_reason("일일 손실 한도")
        assert "Stage 1 거부" in reason

    def test_close_reason_known_triggers(self):
        for trigger in ["stop_loss", "take_profit", "trailing_stop",
                        "drawdown", "emergency", "manual"]:
            reason = DecisionLogger.build_close_reason(trigger)
            assert reason != ""

    def test_close_reason_unknown_trigger(self):
        reason = DecisionLogger.build_close_reason("unknown_trigger")
        assert "unknown_trigger" in reason


class TestAllDecisionTypes:
    """Ensure every decision type can be logged (EXECUTE/SKIP/REJECTED/REDUCE/CLOSE)."""

    @pytest.mark.parametrize("decision", [
        DecisionLogger.DECISION_EXECUTE,
        DecisionLogger.DECISION_SKIP,
        DecisionLogger.DECISION_REJECTED,
        DecisionLogger.DECISION_REDUCE,
        DecisionLogger.DECISION_CLOSE,
    ])
    def test_all_decisions_logged(self, decision):
        saved = {}

        class MockStorage:
            def save_decision(self, **kwargs):
                saved.update(kwargs)

        dl = DecisionLogger(storage=MockStorage())
        record = DecisionLogger.build_record(
            candle_id=f"2024-01-15T12:00:00Z_{decision}",
            market_snapshot=_make_snapshot(),
            model_predictions=_make_predictions(),
            top_features=[],
            signal=_make_signal(),
            risk_check=_make_risk(),
            decision=decision,
            decision_reason=f"테스트: {decision}",
        )
        dl.log(record)
        assert saved.get("decision") == decision
