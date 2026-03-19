"""Risk management parameters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeRiskParams:
    max_position: float
    stop_loss_pct: float
    take_profit_pct: float


# Regime-specific risk overrides (used by regime_detector + risk_engine)
REGIME_PARAMS = {
    "TRENDING": RegimeRiskParams(
        max_position=1.0,
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
    ),
    "RANGING": RegimeRiskParams(
        max_position=0.5,
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
    ),
    "VOLATILE": RegimeRiskParams(
        max_position=0.3,
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
    ),
}

# Drawdown action thresholds
DRAWDOWN_WARN_LEVEL = 0.05       # 5%  → Telegram warning
DRAWDOWN_REDUCE_LEVEL = 0.08     # 8%  → halt new positions, reduce 50%
DRAWDOWN_HALT_LEVEL = 0.10       # 10% → full liquidation, system pause

# Liquidation proximity thresholds (Futures-specific)
LIQ_WARN_PCT = 0.80              # 80% of distance to liquidation → Telegram + reduce 50%
LIQ_EMERGENCY_PCT = 0.90         # 90% → immediate full liquidation

# Funding rate risk threshold
FUNDING_RATE_WARN = 0.001        # ±0.1% per funding period

# Stage 1 pre-trade checks
MAX_SINGLE_ORDER_RATIO = 0.10    # max 10% of balance per order
MAX_DAILY_TRADES = 20
CONSECUTIVE_LOSS_LIMIT = 5       # halt after 5 consecutive losses
CONSECUTIVE_LOSS_COOLDOWN_MIN = 30

# Signal / position sizing
SIGNAL_LOOKBACK_WINDOW = 48      # candles for rolling std normalization
MIN_HOLD_CANDLES = 2             # minimum candles to hold a position
TRAILING_STOP_ACTIVATION_PCT = 0.02   # activate trailing stop at 2% profit
TRAILING_STOP_DISTANCE_PCT = 0.01     # trail 1% from high
