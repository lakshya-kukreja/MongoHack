"""Tests for API healthcheck endpoint and security headers."""

from fastapi.testclient import TestClient
from app.core.config import settings


def test_health_check_success(client: TestClient) -> None:
    """Verify health endpoint returns 200 and expected schema."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["version"] == "1.0.0"


def test_security_headers_present_on_api_routes(client: TestClient) -> None:
    """Verify strict standard security headers are applied to API responses."""
    response = client.get("/api/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    csp = response.headers.get("Content-Security-Policy", "")
    assert csp == "default-src 'self'; frame-ancestors 'none';"
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_docs_csp_in_development(client: TestClient) -> None:
    """Verify /docs has scoped CSP allowing Swagger UI assets in non-production."""
    # Ensure environment is non-production
    original_env = settings.APP_ENV
    try:
        settings.APP_ENV = "development"
        response = client.get("/docs")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        csp = response.headers.get("Content-Security-Policy", "")
        assert "https://cdn.jsdelivr.net" in csp
        assert "https://fastapi.tiangolo.com" in csp
        assert "'unsafe-eval'" not in csp
        assert "frame-ancestors 'none'" in csp
    finally:
        settings.APP_ENV = original_env


def test_docs_csp_in_production(client: TestClient) -> None:
    """Verify /docs retains strict restrictive CSP in production."""
    original_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        response = client.get("/docs")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        csp = response.headers.get("Content-Security-Policy", "")
        assert csp == "default-src 'self'; frame-ancestors 'none';"
        assert "https://cdn.jsdelivr.net" not in csp
        assert "'unsafe-inline'" not in csp
    finally:
        settings.APP_ENV = original_env

