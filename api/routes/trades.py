"""Trade history endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_trades(limit: int = 500) -> list[dict[str, Any]]:
    from data.storage import Storage
    storage = Storage()
    trades = storage.get_trades(limit=limit)
    # Strip SQLAlchemy internal state
    return [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in (trades or [])
    ]
