"""Integration tests verifying FastAPI endpoints with MongoDB storage backend."""

import pytest
from typing import Generator
from fastapi.testclient import TestClient
from app.main import create_app
from app.models.event import EventRecord
from app.services.storage import StorageService, get_storage_service, set_storage_service
from tests.mock_mongo import MockDatabase, MockMongoClient


@pytest.fixture
def mongo_client_and_storage() -> Generator[tuple[TestClient, StorageService, MockDatabase], None, None]:
    """Test client and storage configured with mock MongoDB database."""
    mock_client = MockMongoClient(ping_healthy=True)
    db = mock_client["incident_investigator"]
    storage = StorageService(database=db)
    storage.create_indexes()
    set_storage_service(storage)

    app = create_app()
    app.dependency_overrides[get_storage_service] = lambda: storage
    with TestClient(app) as test_client:
        yield test_client, storage, db
    app.dependency_overrides.clear()


def test_mongo_api_health_success(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase]
) -> None:
    """Verify /api/health returns ok and connected status when MongoDB responds to ping."""
    client, _, _ = mongo_client_and_storage
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["version"] == "1.0.0"


def test_mongo_api_health_degraded(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase]
) -> None:
    """Verify /api/health returns degraded and disconnected status when MongoDB ping fails."""
    client, _, db = mongo_client_and_storage
    db.client.admin.ping_healthy = False

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"


def test_mongo_api_ingest_and_timeline_lifecycle(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase]
) -> None:
    """Verify ingestion persists to MongoDB and timeline reflects persisted events."""
    client, storage, db = mongo_client_and_storage

    payload = {
        "incident_id": "INC-MONGO-100",
        "events": [
            {
                "source_id": "ALERT-1",
                "timestamp": "2026-10-30T14:02:00Z",
                "source_type": "monitoring_alert",
                "author_or_actor": "datadog-monitor",
                "channel_or_service": "checkout-service",
                "summary": "High latency alert",
                "raw_content": "P99 latency > 2000ms",
            },
            {
                "source_id": "SLACK-1",
                "timestamp": "2026-10-30T14:05:00Z",
                "source_type": "slack",
                "author_or_actor": "alice.dev",
                "channel_or_service": "#incidents",
                "summary": "Alice investigating latency",
                "raw_content": "Looking into the checkout service now",
            },
        ],
    }

    # Ingest batch
    resp = client.post("/api/incidents/ingest", json=payload)
    assert resp.status_code == 201
    ingest_data = resp.json()
    assert ingest_data["incident_id"] == "INC-MONGO-100"
    assert ingest_data["ingested_count"] == 2
    assert ingest_data["status"] == "success"

    # Verify timeline
    timeline_resp = client.get("/api/incidents/INC-MONGO-100/timeline")
    assert timeline_resp.status_code == 200
    t_data = timeline_resp.json()
    assert t_data["incident_id"] == "INC-MONGO-100"
    assert t_data["total_events"] == 2
    assert t_data["filtered_count"] == 2
    assert len(t_data["events"]) == 2
    assert t_data["events"][0]["source_id"] == "ALERT-1"
    assert t_data["events"][1]["source_id"] == "SLACK-1"

    # Verify event detail endpoint
    event_resp = client.get("/api/incidents/INC-MONGO-100/events/ALERT-1")
    assert event_resp.status_code == 200
    ev = event_resp.json()
    assert ev["source_id"] == "ALERT-1"
    assert ev["channel_or_service"] == "checkout-service"


def test_mongo_api_reingestion_duplicate_prevention(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase]
) -> None:
    """Verify that re-ingesting an event updates it without creating duplicate records."""
    client, _, _ = mongo_client_and_storage

    initial_payload = {
        "incident_id": "INC-MONGO-DUP",
        "events": [
            {
                "source_id": "DEPLOY-1",
                "timestamp": "2026-10-30T13:45:00Z",
                "source_type": "deployment_log",
                "author_or_actor": "ci-bot",
                "channel_or_service": "auth-service",
                "summary": "Deploy v1.0.0",
                "raw_content": "Starting deploy v1.0.0",
            }
        ],
    }

    resp1 = client.post("/api/incidents/ingest", json=initial_payload)
    assert resp1.status_code == 201
    assert resp1.json()["ingested_count"] == 1

    # Timeline has 1 event
    t1 = client.get("/api/incidents/INC-MONGO-DUP/timeline").json()
    assert t1["total_events"] == 1

    # Re-ingest the same event with updated summary
    updated_payload = {
        "incident_id": "INC-MONGO-DUP",
        "events": [
            {
                "source_id": "DEPLOY-1",
                "timestamp": "2026-10-30T13:45:00Z",
                "source_type": "deployment_log",
                "author_or_actor": "ci-bot",
                "channel_or_service": "auth-service",
                "summary": "Deploy v1.0.0 Finished Successfully",
                "raw_content": "Deploy v1.0.0 finished with status SUCCESS",
            }
        ],
    }

    resp2 = client.post("/api/incidents/ingest", json=updated_payload)
    assert resp2.status_code == 201

    # Timeline must still have only 1 event
    t2 = client.get("/api/incidents/INC-MONGO-DUP/timeline").json()
    assert t2["total_events"] == 1
    assert t2["events"][0]["summary"] == "Deploy v1.0.0 Finished Successfully"


def test_mongo_api_list_incidents(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase],
    sample_demo_events: list[EventRecord],
) -> None:
    """Verify GET /api/incidents returns aggregated summaries from MongoDB."""
    client, storage, _ = mongo_client_and_storage
    storage.insert_events(sample_demo_events)

    response = client.get("/api/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["incident_id"] == "INC-2026-042"
    assert inc["event_count"] == 17
    assert "checkout-service" in inc["services_involved"]
    assert inc["start_time"] != ""
    assert inc["end_time"] != ""


def test_mongo_api_timeline_filtering(
    mongo_client_and_storage: tuple[TestClient, StorageService, MockDatabase],
    sample_demo_events: list[EventRecord],
) -> None:
    """Verify date window and source_type query parameters against MongoDB."""
    client, storage, _ = mongo_client_and_storage
    storage.insert_events(sample_demo_events)

    # Filter by source_type
    resp = client.get("/api/incidents/INC-2026-042/timeline?source_type=monitoring_alert")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 17
    assert data["filtered_count"] > 0
    assert all(ev["source_type"] == "monitoring_alert" for ev in data["events"])

    # Filter by time window
    resp = client.get(
        "/api/incidents/INC-2026-042/timeline?start_time=2026-10-30T14:00:00Z&end_time=2026-10-30T14:10:00Z"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 17
    assert data["filtered_count"] > 0
    assert data["filtered_count"] < 17

