"""Real-time metric collection for Aegis.

Maintains an in-memory snapshot of the latest system metrics,
updated on every candle cycle by the orchestrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """Current system state snapshot."""
    # Timing
    last_candle_ts: str = ""
    last_update_ts: str = ""

    # Account
    balance_usdt: float = 0.0
    unrealized_pnl: float = 0.0

    # Position
    position_side: str = "FLAT"
    position_size: float = 0.0
    entry_price: float = 0.0
    liquidation_price: float = 0.0
    leverage: int = 3

    # Signal
    last_z_score: float = 0.0
    last_direction: str = "FLAT"
    last_prediction: float = 0.0

    # Market
    current_price: float = 0.0
    funding_rate: float = 0.0

    # Performance
    daily_pnl_pct: float = 0.0
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    drawdown_pct: float = 0.0

    # System
    is_running: bool = False
    last_error: str = ""
    candle_count: int = 0


class MetricsCollector:
    """Collects and exposes real-time system metrics."""

    def __init__(self) -> None:
        self._metrics = SystemMetrics()

    def update(self, **kwargs: Any) -> None:
        """Update one or more metric fields."""
        for key, value in kwargs.items():
            if hasattr(self._metrics, key):
                setattr(self._metrics, key, value)
            else:
                logger.warning("Unknown metric field: %s", key)
        self._metrics.last_update_ts = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        """Return a dict snapshot of all current metrics."""
        from dataclasses import asdict
        return asdict(self._metrics)

    def record_candle(
        self,
        candle_ts: str,
        price: float,
        balance: float,
        unrealized_pnl: float,
    ) -> None:
        """Called each candle to update core market metrics."""
        self._metrics.last_candle_ts = candle_ts
        self._metrics.current_price = price
        self._metrics.balance_usdt = balance
        self._metrics.unrealized_pnl = unrealized_pnl
        self._metrics.candle_count += 1
        self._metrics.last_update_ts = datetime.now(timezone.utc).isoformat()

    def record_signal(self, z_score: float, direction: str, prediction: float) -> None:
        self._metrics.last_z_score = z_score
        self._metrics.last_direction = direction
        self._metrics.last_prediction = prediction

    def record_position(
        self,
        side: str,
        size: float,
        entry_price: float,
        liquidation_price: float,
        leverage: int,
    ) -> None:
        self._metrics.position_side = side
        self._metrics.position_size = size
        self._metrics.entry_price = entry_price
        self._metrics.liquidation_price = liquidation_price
        self._metrics.leverage = leverage

    def record_trade_result(self, pnl_pct: float, win: bool) -> None:
        self._metrics.total_trades += 1
        if win:
            wins = round(self._metrics.win_rate * (self._metrics.total_trades - 1)) + 1
        else:
            wins = round(self._metrics.win_rate * (self._metrics.total_trades - 1))
        self._metrics.win_rate = wins / self._metrics.total_trades

    def set_running(self, running: bool) -> None:
        self._metrics.is_running = running

    def set_error(self, error: str) -> None:
        self._metrics.last_error = error
        logger.error("System error recorded: %s", error)


# Module-level singleton
collector = MetricsCollector()
