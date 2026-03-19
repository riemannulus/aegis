"""Decision log query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class DecisionResponse(BaseModel):
    timestamp: int
    decision: str
    direction: str | None
    z_score: float | None
    regime: str | None
    reason: str | None
    full_record: Any | None


@router.get("/", response_model=list[DecisionResponse])
async def get_decisions(limit: int = Query(default=50, le=500)):
    from data.storage import Storage
    storage = Storage()
    rows = storage.get_decisions(limit=limit)
    return [
        DecisionResponse(
            timestamp=r.get("timestamp", 0),
            decision=r.get("decision", ""),
            direction=r.get("direction"),
            z_score=r.get("z_score"),
            regime=r.get("regime"),
            reason=r.get("reason"),
            full_record=r.get("full_record"),
        )
        for r in rows
    ]
