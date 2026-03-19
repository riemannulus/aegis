"""Analytics query endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PnLSummary(BaseModel):
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe: float | None
    max_drawdown: float | None


@router.get("/pnl-summary", response_model=PnLSummary)
async def get_pnl_summary():
    from data.storage import Storage
    storage = Storage()
    trades = storage.get_trades(limit=1000)
    if not trades:
        return PnLSummary(total_trades=0, win_rate=0.0, total_pnl=0.0, sharpe=None, max_drawdown=None)

    import numpy as np
    pnls = [t["pnl"] for t in trades if "pnl" in t]
    total_pnl = sum(pnls)
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0.0

    pnl_arr = np.array(pnls)
    sharpe = float(pnl_arr.mean() / pnl_arr.std() * np.sqrt(252)) if len(pnl_arr) > 1 and pnl_arr.std() > 0 else None

    cumulative = np.cumsum(pnl_arr)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (running_max - cumulative) / (running_max + 1e-9)
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else None

    return PnLSummary(
        total_trades=len(pnls),
        win_rate=win_rate,
        total_pnl=total_pnl,
        sharpe=sharpe,
        max_drawdown=max_dd,
    )
