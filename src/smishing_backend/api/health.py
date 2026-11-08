"""Health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from smishing_backend.services.health import health_status

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status=health_status())
