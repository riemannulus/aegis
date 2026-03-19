"""System control endpoints — start, stop, configure."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_system_running = False


class SystemStatus(BaseModel):
    running: bool
    testnet: bool
    symbol: str
    timeframe: str


class ControlResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=SystemStatus)
async def get_status():
    from config.settings import settings
    return SystemStatus(
        running=_system_running,
        testnet=settings.USE_TESTNET,
        symbol=settings.TRADING_SYMBOL,
        timeframe=settings.TIMEFRAME,
    )


@router.post("/start", response_model=ControlResponse)
async def start_system():
    global _system_running
    if _system_running:
        return ControlResponse(success=False, message="System already running")
    _system_running = True
    return ControlResponse(success=True, message="System started")


@router.post("/stop", response_model=ControlResponse)
async def stop_system():
    global _system_running
    if not _system_running:
        return ControlResponse(success=False, message="System not running")
    _system_running = False
    return ControlResponse(success=True, message="System stopped")
