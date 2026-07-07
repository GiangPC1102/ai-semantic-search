from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.const.healthcheck import *

router = APIRouter()

class HealthCheckResponse(BaseModel):
    """Health check response payload."""

    status: str
    service: str
    environment: str


@router.get("/", response_model=HealthCheckResponse)
async def healthcheck() -> HealthCheckResponse:
    """Return service health status."""
    return HealthCheckResponse(
        status=HEALTH_STATUS_OK,
        service=SERVICE_NAME,
        environment=settings.PREFIX,
    )
