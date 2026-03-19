"""FastAPI entrypoint for Aegis trading system."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import health, signals, positions, decisions, analytics, control
from api.websocket import router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Aegis API starting up")
    yield
    logger.info("Aegis API shutting down")


app = FastAPI(
    title="Aegis Trading API",
    description="AI Crypto Futures Auto-Trading System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(signals.router, prefix="/signals", tags=["signals"])
app.include_router(positions.router, prefix="/positions", tags=["positions"])
app.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(control.router, prefix="/control", tags=["control"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])
