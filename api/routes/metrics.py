"""Daily metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class DailyMetrics(BaseModel):
    today_realized_pnl: float
    today_funding_cost: float
    unrealized_pnl: float | None
    total_trades_today: int
    account_balance: float


@router.get("/", response_model=DailyMetrics)
async def get_metrics():
    import time
    from data.storage import Storage, Position
    storage = Storage()

    # Today's start in ms (UTC midnight)
    now_ms = int(time.time() * 1000)
    day_start_ms = now_ms - (now_ms % 86_400_000)

    trades = storage.get_trades(limit=10000)
    today_trades = [t for t in trades if t.get("timestamp", 0) >= day_start_ms]
    today_pnl = sum(t.get("pnl", 0.0) for t in today_trades)
    today_funding = sum(t.get("funding_cost", 0.0) for t in today_trades)

    with storage._session() as sess:
        pos = (
            sess.query(Position)
            .order_by(Position.timestamp.desc())
            .first()
        )
        unrealized = pos.unrealized_pnl if pos else None

    return DailyMetrics(
        today_realized_pnl=today_pnl,
        today_funding_cost=today_funding,
        unrealized_pnl=unrealized,
        total_trades_today=len(today_trades),
        account_balance=0.0,
    )
