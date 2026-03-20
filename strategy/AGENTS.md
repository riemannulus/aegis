<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-20 | Updated: 2026-03-20 -->

# strategy

## Purpose
Trading strategy logic: converts raw model predictions into actionable position signals, manages position sizing, detects market regimes, and logs all trading decisions for audit.

## Key Files

| File | Description |
|------|-------------|
| `signal_converter.py` | `SignalConverter` — Transforms ensemble predictions into `SignalResult` via 5-stage pipeline: Z-score normalization → threshold gate → cost filter → direction confirmation (2 consecutive) → min hold-time filter |
| `position_manager.py` | `PositionManager` — Tracks Futures position state (`PositionState`) and computes `OrderIntent` (OPEN/CLOSE/FLIP/REDUCE/NONE) to reach target position |
| `regime_detector.py` | Market regime detection (volatile/normal) — adjusts risk parameters per regime |
| `decision_logger.py` | `DecisionLogger` — Persists every decision (trade or skip) to SQLite for audit trail |

## For AI Agents

### Working In This Directory
- `SignalResult` dataclass is the main output: `direction` (LONG/SHORT/FLAT), `size_ratio`, `z_score`, `reason`
- `OrderIntent` dataclass tells execution layer what orders to place: `action`, `close_size`, `open_side`, `open_size`
- Direction changes require 2 consecutive confirming signals (anti-whipsaw)
- `MIN_SIGNAL_THRESHOLD` (default 1.0 Z-score) gates all trading — below threshold = FLAT
- Position manager handles complex transitions: FLIP_TO_LONG, FLIP_TO_SHORT (close + reopen)

### Testing Requirements
- `test_signal_converter.py` and `test_decision_logger.py` in tests/
- Test edge cases: rapid direction changes, threshold boundary, min hold violations

### Common Patterns
- `signal = converter.convert(prediction)` — main entry point
- `intent = position_manager.compute_order_intent(direction, ratio, balance)` — order computation
- Decision logger records both executed trades AND skipped signals with reasons

## Dependencies

### Internal
- `config/settings.py` — Threshold, risk parameters
- `data/storage.py` — Decision persistence (via DecisionLogger)

### External
- `numpy` — Z-score computation

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
