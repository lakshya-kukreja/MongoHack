"""Integration tests for FastAPI REST API endpoints."""

from fastapi.testclient import TestClient
from app.models.event import EventRecord
from app.services.storage import StorageService


def test_ingest_and_timeline_lifecycle(
    client: TestClient, sample_demo_events: list[EventRecord]
) -> None:
    """Test full cycle: ingest demo events, list incidents, fetch timeline, fetch single event."""
    # 1. Ingest
    payload = {
        "incident_id": "INC-2026-042",
        "events": [e.model_dump(mode="json") for e in sample_demo_events],
    }
    ingest_res = client.post("/api/incidents/ingest", json=payload)
    assert ingest_res.status_code == 201
    ingest_data = ingest_res.json()
    assert ingest_data["incident_id"] == "INC-2026-042"
    assert ingest_data["ingested_count"] == 17
    assert ingest_data["status"] == "success"

    # 2. List incidents
    list_res = client.get("/api/incidents")
    assert list_res.status_code == 200
    incidents = list_res.json()
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["incident_id"] == "INC-2026-042"
    assert inc["event_count"] == 17
    assert inc["start_time"] == "2026-10-30T13:45:00Z"
    assert inc["end_time"] == "2026-10-30T14:45:00Z"
    assert "checkout-service" in inc["services_involved"]

    # 3. Fetch full timeline
    timeline_res = client.get("/api/incidents/INC-2026-042/timeline")
    assert timeline_res.status_code == 200
    timeline_data = timeline_res.json()
    assert timeline_data["incident_id"] == "INC-2026-042"
    assert timeline_data["total_events"] == 17
    assert timeline_data["filtered_count"] == 17
    events = timeline_data["events"]
    assert len(events) == 17
    # Verify chronological ascending order
    for i in range(len(events) - 1):
        assert events[i]["timestamp"] <= events[i + 1]["timestamp"]

    # 4. Fetch single event detail
    event_res = client.get("/api/incidents/INC-2026-042/events/ALERT-201")
    assert event_res.status_code == 200
    ev = event_res.json()
    assert ev["source_id"] == "ALERT-201"
    assert ev["incident_id"] == "INC-2026-042"
    assert ev["source_type"] == "monitoring_alert"
    assert ev["channel_or_service"] == "checkout-service"
    assert "p99_latency" in ev["structured_payload"].get("metric", "") or "p99" in str(ev["structured_payload"])


def test_timeline_query_filtering(
    client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService
) -> None:
    """Test timeline query parameters: start_time, end_time, and source_type."""
    reset_storage.insert_events(sample_demo_events)

    # Time window filter
    res = client.get(
        "/api/incidents/INC-2026-042/timeline",
        params={
            "start_time": "2026-10-30T14:00:00Z",
            "end_time": "2026-10-30T14:15:00Z",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_events"] == 17
    assert data["filtered_count"] > 0
    for ev in data["events"]:
        assert ev["timestamp"] >= "2026-10-30T14:00:00Z"
        assert ev["timestamp"] <= "2026-10-30T14:15:00Z"

    # Source type filter
    slack_res = client.get(
        "/api/incidents/INC-2026-042/timeline",
        params={"source_type": "slack"},
    )
    assert slack_res.status_code == 200
    slack_data = slack_res.json()
    for ev in slack_data["events"]:
        assert ev["source_type"] == "slack"


def test_timeline_unknown_incident_404(client: TestClient) -> None:
    """Verify unknown incident returns 404."""
    res = client.get("/api/incidents/NON_EXISTENT_INC/timeline")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_timeline_invalid_timestamp_422(
    client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService
) -> None:
    """Verify invalid ISO-8601 timestamp parameter returns 422."""
    reset_storage.insert_events(sample_demo_events)
    res = client.get(
        "/api/incidents/INC-2026-042/timeline",
        params={"start_time": "not-a-timestamp"},
    )
    assert res.status_code == 422
    assert "Invalid ISO-8601 datetime format for start_time/end_time" in res.json()["detail"]


def test_timeline_start_time_after_end_time_422(
    client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService
) -> None:
    """Verify start_time after end_time returns 422."""
    reset_storage.insert_events(sample_demo_events)
    res = client.get(
        "/api/incidents/INC-2026-042/timeline",
        params={
            "start_time": "2026-10-30T15:00:00Z",
            "end_time": "2026-10-30T14:00:00Z",
        },
    )
    assert res.status_code == 422
    assert "start_time cannot be after end_time" in res.json()["detail"]


def test_timeline_invalid_source_type_422(
    client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService
) -> None:
    """Verify unrecognized source_type returns 422."""
    reset_storage.insert_events(sample_demo_events)
    res = client.get(
        "/api/incidents/INC-2026-042/timeline",
        params={"source_type": "invalid_source"},
    )
    assert res.status_code == 422
    assert "Invalid source_type" in res.json()["detail"]


def test_event_detail_not_found(
    client: TestClient, sample_demo_events: list[EventRecord], reset_storage: StorageService
) -> None:
    """Verify 404 when requested event ID does not exist."""
    reset_storage.insert_events(sample_demo_events)
    res = client.get("/api/incidents/INC-2026-042/events/NON-EXISTENT-ID")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_ingest_malformed_event_fails_422(client: TestClient) -> None:
    """Verify malformed event records in ingestion body return 422."""
    payload = {
        "incident_id": "INC-2026-042",
        "events": [
            {
                "source_id": "ALERT-1",
                "timestamp": "bad-timestamp",
                "message": "Sample",
            }
        ],
    }
    res = client.post("/api/incidents/ingest", json=payload)
    assert res.status_code == 422
