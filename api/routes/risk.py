"""Risk status and events endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class RiskStatus(BaseModel):
    current_drawdown_pct: float = 0.0
    daily_loss_used_pct: float = 0.0
    position_ratio: float = 0.0
    consecutive_losses: int = 0
    daily_trades: int = 0
    effective_leverage: float = 0.0
    high_water_mark: float = 0.0
    current_equity: float = 0.0
    risk_level: str = "low"
    liquidation_proximity_history: list = []


@router.get("/status", response_model=RiskStatus)
async def get_risk_status():
    from data.storage import Storage, Trade, Position
    from datetime import datetime, timezone
    storage = Storage()
    trades = storage.get_trades(limit=10000)

    if not trades:
        return RiskStatus()

    import time
    import numpy as np

    pnls = [t.get("pnl", 0.0) for t in trades]
    pnl_arr = np.array(pnls)
    cumulative = np.cumsum(pnl_arr)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (running_max - cumulative) / (running_max + 1e-9)
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0

    initial_capital = 10000.0
    equity = initial_capital + float(cumulative[-1]) if len(cumulative) > 0 else initial_capital
    hwm = initial_capital + float(running_max.max()) if len(running_max) > 0 else initial_capital

    now_ms = int(time.time() * 1000)
    day_start_ms = now_ms - (now_ms % 86_400_000)
    today_trades = [t for t in trades if t.get("timestamp", 0) >= day_start_ms]
    daily_loss = sum(t.get("pnl", 0.0) for t in today_trades)
    daily_loss_pct = abs(min(daily_loss, 0.0)) / (initial_capital * 0.05)  # as pct of 5% limit

    cons_losses = 0
    for t in sorted(trades, key=lambda t: t.get("timestamp", 0), reverse=True):
        if t.get("pnl", 0.0) < 0:
            cons_losses += 1
        else:
            break

    if max_dd > 0.10 or cons_losses >= 5:
        risk_level = "high"
    elif max_dd > 0.05 or cons_losses >= 3:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Get current position for effective leverage
    effective_lev = 0.0
    with storage._session() as sess:
        pos = sess.query(Position).order_by(Position.timestamp.desc()).first()
        if pos and pos.size > 0:
            effective_lev = 3.0  # default leverage

    return RiskStatus(
        current_drawdown_pct=max_dd,
        daily_loss_used_pct=daily_loss_pct,
        position_ratio=0.0,
        consecutive_losses=cons_losses,
        daily_trades=len(today_trades),
        effective_leverage=effective_lev,
        high_water_mark=hwm,
        current_equity=equity,
        risk_level=risk_level,
    )


@router.get("/events")
async def get_risk_events(limit: int = 100) -> list[dict[str, Any]]:
    return []
