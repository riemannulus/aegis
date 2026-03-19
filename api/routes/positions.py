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
