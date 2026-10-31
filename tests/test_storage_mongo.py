"""Automated unit tests for persistent MongoDB Atlas operations in StorageService."""

import pytest
from datetime import datetime, timezone
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from app.core.config import settings
from app.models.event import EventRecord, SourceType
from app.services.storage import StorageService
from tests.mock_mongo import MockDatabase, MockMongoClient


@pytest.fixture
def mock_mongo_db() -> MockDatabase:
    """Fixture providing a fresh mock MongoDB database."""
    client = MockMongoClient(db_name="incident_investigator")
    return client["incident_investigator"]


def test_mongo_create_indexes(mock_mongo_db: MockDatabase) -> None:
    """Verify all required MongoDB indexes are created with appropriate uniqueness and ordering."""
    storage = StorageService(database=mock_mongo_db)
    storage.create_indexes()

    indexes = mock_mongo_db["incident_events"].indexes
    assert "incident_source_id_unique" in indexes
    assert indexes["incident_source_id_unique"]["unique"] is True
    assert indexes["incident_source_id_unique"]["keys"] == [("incident_id", 1), ("source_id", 1)]

    assert "incident_timestamp_idx" in indexes
    assert indexes["incident_timestamp_idx"]["keys"] == [("incident_id", 1), ("timestamp", 1)]

    assert "timestamp_idx" in indexes
    assert indexes["timestamp_idx"]["keys"] == [("timestamp", 1)]

    assert "source_id_idx" in indexes
    assert indexes["source_id_idx"]["keys"] == [("source_id", 1)]

    assert "source_type_idx" in indexes
    assert indexes["source_type_idx"]["keys"] == [("source_type", 1)]


def test_mongo_insert_and_retrieve_events(
    mock_mongo_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Verify events are stored in MongoDB with native BSON types and retrieved accurately."""
    storage = StorageService(database=mock_mongo_db)
    assert not storage.is_in_memory
    assert storage.ping() is True

    # Ingest full demo batch
    count = storage.insert_events(sample_demo_events)
    assert count == len(sample_demo_events)
    assert count == 17

    # Verify documents in collection
    raw_docs = mock_mongo_db["incident_events"].docs
    assert len(raw_docs) == 17
    sample_doc = raw_docs[0]
    assert isinstance(sample_doc["timestamp"], datetime)
    assert sample_doc["timestamp"].tzinfo == timezone.utc
    assert isinstance(sample_doc["source_type"], str)

    # Verify existence and counting
    assert storage.incident_exists("INC-2026-042") is True
    assert storage.incident_exists("NON-EXISTENT") is False
    assert storage.count_events("INC-2026-042") == 17

    # Verify individual event retrieval
    event = storage.get_event("INC-2026-042", "ALERT-201")
    assert event is not None
    assert event.source_id == "ALERT-201"
    assert event.incident_id == "INC-2026-042"
    assert event.source_type == SourceType.MONITORING_ALERT

    # Verify all events returned sorted chronologically
    all_events = storage.get_all_incident_events("INC-2026-042")
    assert len(all_events) == 17
    for i in range(len(all_events) - 1):
        assert all_events[i].timestamp <= all_events[i + 1].timestamp


def test_mongo_duplicate_event_handling(mock_mongo_db: MockDatabase) -> None:
    """Verify duplicate prevention and idempotent upsert behavior in MongoDB storage."""
    storage = StorageService(database=mock_mongo_db)
    storage.create_indexes()

    event1 = EventRecord(
        source_id="ALERT-201",
        incident_id="INC-2026-042",
        timestamp=datetime(2026, 10, 30, 14, 5, 0, tzinfo=timezone.utc),
        source_type=SourceType.MONITORING_ALERT,
        author_or_actor="datadog-monitor",
        channel_or_service="checkout-service",
        summary="Initial alert summary",
        raw_content="P99 latency breach",
    )

    # First ingestion
    storage.insert_events([event1])
    assert storage.count_events("INC-2026-042") == 1
    assert storage.get_event("INC-2026-042", "ALERT-201").summary == "Initial alert summary"

    # Re-ingest the exact same source event with an updated summary and payload
    event1_updated = EventRecord(
        source_id="ALERT-201",
        incident_id="INC-2026-042",
        timestamp=datetime(2026, 10, 30, 14, 5, 0, tzinfo=timezone.utc),
        source_type=SourceType.MONITORING_ALERT,
        author_or_actor="datadog-monitor",
        channel_or_service="checkout-service",
        summary="Updated alert summary (enriched)",
        raw_content="P99 latency breach (enriched details)",
    )

    storage.insert_events([event1_updated])

    # Event count must remain 1 (no duplicate document created)
    assert storage.count_events("INC-2026-042") == 1
    # Document content must be updated
    updated_retrieved = storage.get_event("INC-2026-042", "ALERT-201")
    assert updated_retrieved is not None
    assert updated_retrieved.summary == "Updated alert summary (enriched)"

    # Direct insertion of a duplicate without upsert must violate the unique index
    with pytest.raises(DuplicateKeyError):
        mock_mongo_db["incident_events"].insert_one(event1.model_dump())


def test_mongo_persistence_across_restarts(
    mock_mongo_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Verify that events persist in MongoDB and are accessible after storage service reinitialization."""
    # Lifecycle 1: Application starts and ingests events
    storage_instance_1 = StorageService(database=mock_mongo_db)
    storage_instance_1.insert_events(sample_demo_events)
    assert storage_instance_1.count_events("INC-2026-042") == 17

    # Lifecycle 2: Application restarts, creating a new StorageService instance connected to the same DB
    storage_instance_2 = StorageService(database=mock_mongo_db)
    assert storage_instance_2.incident_exists("INC-2026-042") is True
    assert storage_instance_2.count_events("INC-2026-042") == 17

    # Events are intact and sorted
    events_after_restart = storage_instance_2.get_all_incident_events("INC-2026-042")
    assert len(events_after_restart) == 17
    assert events_after_restart[0].source_id == "DEPLOY-101"

    event_detail = storage_instance_2.get_event("INC-2026-042", "ALERT-201")
    assert event_detail is not None
    assert event_detail.author_or_actor == "datadog-monitor"


def test_mongo_timeline_filtering(
    mock_mongo_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Verify deterministic timeline filtering against MongoDB-backed storage."""
    storage = StorageService(database=mock_mongo_db)
    storage.insert_events(sample_demo_events)

    # Filter by date window (14:00 to 14:15)
    window_events = storage.get_timeline_events(
        incident_id="INC-2026-042",
        start_time="2026-10-30T14:00:00Z",
        end_time="2026-10-30T14:15:00Z",
    )
    assert len(window_events) > 0
    assert len(window_events) < 17

    # Filter by source_type = slack
    slack_events = storage.get_timeline_events(
        incident_id="INC-2026-042",
        source_types="slack",
    )
    assert len(slack_events) > 0
    for ev in slack_events:
        assert ev.source_type == SourceType.SLACK


def test_mongo_list_incidents_aggregation(
    mock_mongo_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Verify list_incidents performs MongoDB aggregation producing valid IncidentSummary records."""
    storage = StorageService(database=mock_mongo_db)
    storage.insert_events(sample_demo_events)

    summaries = storage.list_incidents()
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.incident_id == "INC-2026-042"
    assert summary.event_count == 17
    assert summary.start_time != ""
    assert summary.end_time != ""
    assert "checkout-service" in summary.services_involved
    assert summary.title != ""


def test_mongo_clear_data(
    mock_mongo_db: MockDatabase, sample_demo_events: list[EventRecord]
) -> None:
    """Verify clear_data removes incident records from MongoDB collection."""
    storage = StorageService(database=mock_mongo_db)
    storage.insert_events(sample_demo_events)
    assert storage.count_events("INC-2026-042") == 17

    # Clear specific incident
    storage.clear_data("INC-2026-042")
    assert storage.incident_exists("INC-2026-042") is False
    assert storage.count_events("INC-2026-042") == 0


def test_mongo_ping_success_and_failure() -> None:
    """Verify ping returns True when healthy and False when connection check fails."""
    # Healthy database client
    healthy_client = MockMongoClient(ping_healthy=True)
    healthy_storage = StorageService(database=healthy_client["incident_investigator"])
    assert healthy_storage.ping() is True

    # Failing database client (simulating Atlas network outage / bad credentials)
    unhealthy_client = MockMongoClient(ping_healthy=False)
    unhealthy_storage = StorageService(database=unhealthy_client["incident_investigator"])
    assert unhealthy_storage.ping() is False

    # When MONGODB_URI is configured but connection failed (db is None)
    original_uri = settings.MONGODB_URI
    try:
        settings.MONGODB_URI = "mongodb+srv://test:test@cluster.mongodb.net"
        disconnected_storage = StorageService(database=None, force_in_memory=False)
        assert disconnected_storage.ping() is False
    finally:
        settings.MONGODB_URI = original_uri

