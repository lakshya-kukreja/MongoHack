"""API routes package."""

from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(incidents_router)

__all__ = ["api_router"]
