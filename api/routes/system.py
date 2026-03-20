"""System info endpoints — logs, scheduler, latency."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/logs")
async def get_logs(level: str = "INFO", limit: int = 200) -> list[dict[str, Any]]:
    # Return in-memory log records captured by logging framework
    root_logger = logging.getLogger()
    level_no = getattr(logging, level.upper(), logging.INFO)

    records: list[dict[str, Any]] = []
    for handler in logging.root.handlers:
        if hasattr(handler, "buffer"):
            for record in handler.buffer[-limit:]:
                if record.levelno >= level_no:
                    records.append({
                        "timestamp": int(record.created * 1000),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    })
    return records[-limit:]


@router.get("/scheduler")
async def get_scheduler_status() -> dict[str, Any]:
    return {
        "running": False,
        "jobs": [],
        "next_run": None,
    }


@router.get("/latency")
async def get_pipeline_latency() -> dict[str, Any]:
    return {
        "data_fetch_ms": None,
        "feature_compute_ms": None,
        "model_predict_ms": None,
        "decision_ms": None,
        "total_ms": None,
        "measured_at": int(time.time() * 1000),
    }
