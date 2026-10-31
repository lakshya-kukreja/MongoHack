"""FastAPI application factory and lifespan management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from app.api import api_router
from app.core.config import settings
from app.core.db import close_mongo_client
from app.core.logging import logger
from app.services.ingestion import parse_incident_data
from app.services.storage import get_storage_service, reset_storage_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    logger.info("Initializing Incident Timeline Investigator API...")
    storage = get_storage_service()

    # Pre-populate sample incident if database/store is empty
    sample_file = Path("data/incidents/inc_2026_042.json")
    if not sample_file.exists():
        # Fallback check relative to repo root
        sample_file = Path("../data/incidents/inc_2026_042.json")

    if sample_file.exists():
        try:
            records = parse_incident_data(sample_file)
            incident_id = records[0].incident_id if records else "INC-2026-042"
            if not storage.incident_exists(incident_id):
                inserted = storage.insert_events(records)
                logger.info(f"Loaded demo dataset: {inserted} records for {incident_id}")
        except Exception as exc:
            logger.warning(f"Could not preload demo dataset: {exc}")

    yield

    logger.info("Shutting down Incident Timeline Investigator API...")
    close_mongo_client()
    reset_storage_service()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Incident Timeline Investigator API",
        description="Grounded RAG & Deterministic Timeline Analysis Engine",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS Middleware
    origins = settings.CORS_ORIGINS
    if isinstance(origins, str):
        origins = [orig.strip() for orig in origins.split(",") if orig.strip()]

    is_wildcard = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if is_wildcard else origins,
        allow_credentials=False if is_wildcard else True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security Headers Middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"

        path = request.url.path.rstrip("/")
        is_docs_route = path in {"/docs", "/redoc"} or request.url.path.startswith("/docs/")

        if is_docs_route and settings.APP_ENV.lower() != "production":
            # Scoped development policy to allow Swagger UI & ReDoc CDN assets without unsafe-eval
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "font-src 'self' data: https://cdn.jsdelivr.net;"
            )
        return response

    # Mount API routers under prefix /api
    app.include_router(api_router)

    return app


app = create_app()
