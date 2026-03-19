"""Real-time WebSocket endpoint for live system state."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Active connections registry
_connections: list[WebSocket] = []


async def broadcast(data: dict[str, Any]) -> None:
    """Broadcast a JSON message to all connected WebSocket clients."""
    dead = []
    for ws in _connections:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.remove(ws)


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """WebSocket endpoint that streams live system state updates."""
    await websocket.accept()
    _connections.append(websocket)
    logger.info("WebSocket client connected. Total: %d", len(_connections))

    try:
        while True:
            # Send periodic heartbeat with latest metrics
            try:
                from monitor.metrics import collector
                snapshot = collector.snapshot()
                await websocket.send_text(json.dumps({"type": "metrics", "data": snapshot}))
            except Exception as exc:
                logger.debug("metrics snapshot error: %s", exc)
                await websocket.send_text(json.dumps({"type": "heartbeat"}))

            # Wait for next tick or client message
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        if websocket in _connections:
            _connections.remove(websocket)
