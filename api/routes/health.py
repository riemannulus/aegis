"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    testnet: bool
    version: str = "0.1.0"


@router.get("/", response_model=HealthResponse)
async def health_check():
    from config.settings import settings
    return HealthResponse(status="ok", testnet=settings.USE_TESTNET)
