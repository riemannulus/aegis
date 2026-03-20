"""Health check endpoint."""

from __future__ import annotations

import os
import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_start_time = time.time()


class HealthResponse(BaseModel):
    status: str
    testnet: bool
    environment: str
    version: str = "0.1.0"
    models_loaded: bool = False
    last_signal_at: str | None = None
    uptime: str | None = None
    db_size_mb: float = 0.0


@router.get("/", response_model=HealthResponse)
async def health_check():
    from config.settings import settings

    # Check if models exist
    models_loaded = os.path.isdir("models/saved") and bool(os.listdir("models/saved"))

    # Check last signal
    last_signal_at = None
    try:
        from data.storage import Storage, Signal
        storage = Storage()
        with storage._session() as sess:
            last_sig = sess.query(Signal).order_by(Signal.timestamp.desc()).first()
            if last_sig:
                from datetime import datetime, timezone
                last_signal_at = datetime.fromtimestamp(
                    last_sig.timestamp / 1000, tz=timezone.utc
                ).isoformat()
    except Exception:
        pass

    # DB size
    db_size = 0.0
    db_path = os.environ.get("AEGIS_DB_PATH", "data/aegis.db")
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path) / (1024 * 1024)

    # Uptime
    elapsed = time.time() - _start_time
    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    return HealthResponse(
        status="running",
        testnet=settings.USE_TESTNET,
        environment="TESTNET" if settings.USE_TESTNET else "MAINNET",
        models_loaded=models_loaded,
        last_signal_at=last_signal_at,
        uptime=uptime_str,
        db_size_mb=round(db_size, 2),
    )
