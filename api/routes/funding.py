"""Funding rate history endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_funding_history(limit: int = 50) -> list[dict[str, Any]]:
    from data.storage import Storage
    storage = Storage()
    rates = storage.get_funding_rates("BTCUSDT", limit=limit)
    # Strip SQLAlchemy internal state
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in (rates or [])
    ]
