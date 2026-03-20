"""Analytics query endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PnLSummary(BaseModel):
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe: float | None
    max_drawdown: float | None


class EquityPoint(BaseModel):
    timestamp: int
    equity: float


class PerformanceSummary(BaseModel):
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    max_drawdown: float | None
    avg_trade_pnl: float
    best_trade: float
    worst_trade: float
    profit_factor: float | None
    expected_value: float | None


class Attribution(BaseModel):
    by_model: dict[str, Any]
    by_regime: dict[str, Any]
    by_hour: dict[str, Any]


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


@router.get("/equity-curve", response_model=list[EquityPoint])
async def get_equity_curve():
    from data.storage import Storage
    storage = Storage()
    trades = storage.get_trades(limit=10000)
    if not trades:
        return []
    trades_sorted = sorted(trades, key=lambda t: t.get("timestamp", 0))
    cumulative = 0.0
    result = []
    for t in trades_sorted:
        cumulative += t.get("pnl", 0.0)
        result.append(EquityPoint(timestamp=t["timestamp"], equity=cumulative))
    return result


@router.get("/performance", response_model=PerformanceSummary)
async def get_performance():
    from data.storage import Storage
    storage = Storage()
    trades = storage.get_trades(limit=10000)
    if not trades:
        return PerformanceSummary(
            total_trades=0, win_rate=0.0, total_pnl=0.0,
            sharpe_ratio=None, sortino_ratio=None, calmar_ratio=None, max_drawdown=None,
            avg_trade_pnl=0.0, best_trade=0.0, worst_trade=0.0,
            profit_factor=None, expected_value=None,
        )

    import numpy as np
    pnls = [t.get("pnl", 0.0) for t in trades]
    pnl_arr = np.array(pnls)
    total_pnl = float(pnl_arr.sum())
    win_rate = float((pnl_arr > 0).mean()) if len(pnl_arr) > 0 else 0.0
    avg_pnl = float(pnl_arr.mean()) if len(pnl_arr) > 0 else 0.0

    std = pnl_arr.std()
    sharpe = float(avg_pnl / std * np.sqrt(252)) if std > 0 else None

    neg = pnl_arr[pnl_arr < 0]
    downside_std = neg.std() if len(neg) > 1 else 0.0
    sortino = float(avg_pnl / downside_std * np.sqrt(252)) if downside_std > 0 else None

    cumulative = np.cumsum(pnl_arr)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (running_max - cumulative) / (running_max + 1e-9)
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0
    calmar = float(total_pnl / max_dd) if max_dd > 0 else None

    # Profit factor
    gross_profit = float(pnl_arr[pnl_arr > 0].sum()) if (pnl_arr > 0).any() else 0.0
    gross_loss = float(abs(pnl_arr[pnl_arr < 0].sum())) if (pnl_arr < 0).any() else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

    # Expected value
    avg_win = float(pnl_arr[pnl_arr > 0].mean()) if (pnl_arr > 0).any() else 0.0
    avg_loss = float(pnl_arr[pnl_arr < 0].mean()) if (pnl_arr < 0).any() else 0.0
    expected_value = win_rate * avg_win + (1 - win_rate) * avg_loss

    return PerformanceSummary(
        total_trades=len(pnls),
        win_rate=win_rate,
        total_pnl=total_pnl,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=max_dd if max_dd > 0 else None,
        avg_trade_pnl=avg_pnl,
        best_trade=float(pnl_arr.max()) if len(pnl_arr) > 0 else 0.0,
        worst_trade=float(pnl_arr.min()) if len(pnl_arr) > 0 else 0.0,
        profit_factor=profit_factor,
        expected_value=expected_value,
    )


@router.get("/attribution", response_model=Attribution)
async def get_attribution():
    return Attribution(by_model={}, by_regime={}, by_hour={})
