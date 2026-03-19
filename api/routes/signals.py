"""Signal query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class SignalResponse(BaseModel):
    timestamp: int
    model_name: str
    prediction: float
    position_signal: float


@router.get("/latest", response_model=list[SignalResponse])
async def get_latest_signals(limit: int = Query(default=10, le=100)):
    from data.storage import Storage
    storage = Storage()
    with storage._session() as sess:
        from data.storage import Signal
        rows = (
            sess.query(Signal)
            .order_by(Signal.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            SignalResponse(
                timestamp=r.timestamp,
                model_name=r.model_name,
                prediction=r.prediction,
                position_signal=r.position_signal,
            )
            for r in rows
        ]
