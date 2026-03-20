"""Position query and management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PositionResponse(BaseModel):
    timestamp: int
    side: str
    entry_price: float
    size: float
    unrealized_pnl: float | None
    liquidation_price: float | None


class CurrentPosition(BaseModel):
    side: str
    size: float
    leverage: int
    entry_price: float
    mark_price: float | None
    liquidation_price: float | None
    unrealized_pnl: float | None


@router.get("/", response_model=CurrentPosition)
async def get_position():
    from data.storage import Storage, Position
    storage = Storage()
    with storage._session() as sess:
        row = (
            sess.query(Position)
            .order_by(Position.timestamp.desc())
            .first()
        )
        if row is None:
            return CurrentPosition(
                side="flat", size=0.0, leverage=1,
                entry_price=0.0, mark_price=None,
                liquidation_price=None, unrealized_pnl=None,
            )
        return CurrentPosition(
            side=row.side,
            size=row.size,
            leverage=1,
            entry_price=row.entry_price,
            mark_price=None,
            liquidation_price=row.liquidation_price,
            unrealized_pnl=row.unrealized_pnl,
        )


@router.get("/current", response_model=list[PositionResponse])
async def get_current_positions(limit: int = 5):
    from data.storage import Storage, Position
    storage = Storage()
    with storage._session() as sess:
        rows = (
            sess.query(Position)
            .order_by(Position.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            PositionResponse(
                timestamp=r.timestamp,
                side=r.side,
                entry_price=r.entry_price,
                size=r.size,
                unrealized_pnl=r.unrealized_pnl,
                liquidation_price=r.liquidation_price,
            )
            for r in rows
        ]
