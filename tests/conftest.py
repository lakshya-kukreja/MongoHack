"""Pytest fixtures for incident timeline investigator tests."""

import sys
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in path
tests_dir = Path(__file__).resolve().parent
repo_root = tests_dir.parent
backend_path = repo_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import create_app
from app.models.event import EventRecord
from app.services.ingestion import parse_incident_data
from app.services.storage import StorageService, get_storage_service, set_storage_service


@pytest.fixture(autouse=True)
def reset_storage() -> Generator[StorageService, None, None]:
    """Provide a fresh in-memory StorageService for every test."""
    service = StorageService(force_in_memory=True)
    set_storage_service(service)
    yield service
    service.clear_data()


@pytest.fixture
def client(reset_storage: StorageService) -> Generator[TestClient, None, None]:
    """Test client configured with in-memory storage."""
    app = create_app()
    app.dependency_overrides[get_storage_service] = lambda: reset_storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_demo_events() -> list[EventRecord]:
    """Load the realistic demo dataset from data/incidents/inc_2026_042.json."""
    data_path = repo_root / "data" / "incidents" / "inc_2026_042.json"
    return parse_incident_data(data_path)
