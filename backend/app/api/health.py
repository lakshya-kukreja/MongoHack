"""Health check endpoint."""

from fastapi import APIRouter, Depends
from app.models.event import HealthResponse
from app.services.storage import StorageService, get_storage_service

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(
    storage: StorageService = Depends(get_storage_service),
) -> HealthResponse:
    """Return health status of API and storage layer."""
    is_live = storage.ping()
    db_status = "connected" if is_live else "disconnected"

    return HealthResponse(
        status="ok" if is_live else "degraded",
        database=db_status,
        version="1.0.0",
    )
