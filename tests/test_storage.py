"""Unit tests for StorageService."""

from app.models.event import EventRecord
from app.services.storage import StorageService


def test_storage_service_in_memory_crud(sample_demo_events: list[EventRecord]) -> None:
    """Verify in-memory StorageService operations."""
    storage = StorageService(force_in_memory=True)
    assert storage.is_in_memory
    assert storage.ping() is True

    # Insert events
    count = storage.insert_events(sample_demo_events)
    assert count == 17

    # Check existence and count
    assert storage.incident_exists("INC-2026-042") is True
    assert storage.incident_exists("NON-EXISTENT") is False
    assert storage.count_events("INC-2026-042") == 17

    # Get single event
    event = storage.get_event("INC-2026-042", "ALERT-201")
    assert event is not None
    assert event.source_id == "ALERT-201"

    # List incidents
    summaries = storage.list_incidents()
    assert len(summaries) == 1
    assert summaries[0].incident_id == "INC-2026-042"
    assert summaries[0].event_count == 17

    # Clear data
    storage.clear_data("INC-2026-042")
    assert storage.incident_exists("INC-2026-042") is False
    assert storage.count_events("INC-2026-042") == 0
