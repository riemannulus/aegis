"""Backtest results endpoints."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_BACKTEST_DIRS = ["data/backtest_results", "results"]


def _find_backtest_files() -> list[dict[str, Any]]:
    results = []
    for d in _BACKTEST_DIRS:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(d, fname)
            backtest_id = fname[:-5]  # strip .json
            results.append({
                "id": backtest_id,
                "file": fpath,
                "mtime": os.path.getmtime(fpath),
            })
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


@router.get("/")
async def list_backtests() -> list[dict[str, Any]]:
    files = _find_backtest_files()
    return [{"id": f["id"]} for f in files]


@router.get("/{backtest_id}")
async def get_backtest(backtest_id: str) -> dict[str, Any]:
    for d in _BACKTEST_DIRS:
        fpath = os.path.join(d, f"{backtest_id}.json")
        if os.path.isfile(fpath):
            with open(fpath) as f:
                return json.load(f)
    raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")


class BacktestRunResponse(BaseModel):
    success: bool
    message: str


@router.post("/run", response_model=BacktestRunResponse)
async def run_backtest() -> BacktestRunResponse:
    return BacktestRunResponse(success=True, message="Backtest run triggered (async stub)")
