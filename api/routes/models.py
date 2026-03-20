"""Model metrics endpoints."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

router = APIRouter()

_MODELS_DIR = "models/saved"


@router.get("/metrics")
async def get_model_metrics() -> dict[str, Any]:
    model_files: list[str] = []
    if os.path.isdir(_MODELS_DIR):
        model_files = [
            f for f in os.listdir(_MODELS_DIR)
            if os.path.isfile(os.path.join(_MODELS_DIR, f))
        ]

    last_retrain_at: str | None = None
    if model_files:
        newest = max(
            model_files,
            key=lambda f: os.path.getmtime(os.path.join(_MODELS_DIR, f)),
        )
        import datetime
        mtime = os.path.getmtime(os.path.join(_MODELS_DIR, newest))
        last_retrain_at = datetime.datetime.fromtimestamp(mtime).isoformat()

    return {
        "last_retrain_at": last_retrain_at,
        "next_retrain_at": None,
        "ic_history": [],
        "rank_ic_history": [],
        "direction_accuracy": None,
        "feature_importance": {},
        "prediction_distribution_drift": None,
        "tra_router_activity": {},
        "ensemble_vs_individual": {},
        "model_files": model_files,
    }
