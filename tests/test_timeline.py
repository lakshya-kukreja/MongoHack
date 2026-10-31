"""Tests for deterministic chronological timeline engine."""

import random
from datetime import datetime, timezone
import pytest
from app.models.event import EventRecord, SourceType
from app.services.timeline import (
    build_timeline_response,
    filter_timeline_events,
    sort_events_chronologically,
)


def test_chronological_ordering_guarantee(sample_demo_events: list[EventRecord]) -> None:
    """Verify that even if events are shuffled out of order, sorting restores strict chronology."""
    shuffled = list(sample_demo_events)
    # Shuffle with fixed seed for reproducibility
    random.Random(42).shuffle(shuffled)

    # Ensure it was actually shuffled
    assert [e.source_id for e in shuffled] != [e.source_id for e in sample_demo_events]

    sorted_events = sort_events_chronologically(shuffled)

    # Assert every adjacent pair is non-decreasing in time
    for i in range(len(sorted_events) - 1):
        assert sorted_events[i].timestamp <= sorted_events[i + 1].timestamp

    # The first event in INC-2026-042 is DEPLOY-101 at 13:45:00Z
    assert sorted_events[0].source_id == "DEPLOY-101"
    assert sorted_events[0].timestamp == datetime(2026, 10, 30, 13, 45, 0, tzinfo=timezone.utc)

    # The last event is SLACK-309 at 14:45:00Z
    assert sorted_events[-1].source_id == "SLACK-309"
    assert sorted_events[-1].timestamp == datetime(2026, 10, 30, 14, 45, 0, tzinfo=timezone.utc)


def test_timeline_date_filtering_inclusive(sample_demo_events: list[EventRecord]) -> None:
    """Verify both start_time and end_time boundaries are inclusive."""
    # ALERT-201 is at 14:02:00Z, SLACK-301 is at 14:04:10Z, ALERT-202 is at 14:05:30Z
    filtered = filter_timeline_events(
        events=sample_demo_events,
        start_time="2026-10-30T14:02:00Z",
        end_time="2026-10-30T14:05:30Z",
    )
    source_ids = [e.source_id for e in filtered]
    assert "ALERT-201" in source_ids  # Boundary start
    assert "SLACK-301" in source_ids  # Within window
    assert "ALERT-202" in source_ids  # Boundary end
    assert "DEPLOY-101" not in source_ids  # Prior to window (13:45:00Z)
    assert "SLACK-302" not in source_ids  # After window (14:07:00Z)


def test_timeline_start_time_only(sample_demo_events: list[EventRecord]) -> None:
    """Verify start_time only filters events prior to boundary."""
    filtered = filter_timeline_events(
        events=sample_demo_events,
        start_time="2026-10-30T14:20:00Z",
    )
    for ev in filtered:
        assert ev.timestamp >= datetime(2026, 10, 30, 14, 20, 0, tzinfo=timezone.utc)


def test_timeline_end_time_only(sample_demo_events: list[EventRecord]) -> None:
    """Verify end_time only filters events after boundary."""
    filtered = filter_timeline_events(
        events=sample_demo_events,
        end_time="2026-10-30T14:00:00Z",
    )
    for ev in filtered:
        assert ev.timestamp <= datetime(2026, 10, 30, 14, 0, 0, tzinfo=timezone.utc)
    source_ids = [e.source_id for e in filtered]
    assert source_ids == ["DEPLOY-101", "SLACK-300"]


def test_timeline_source_type_filter(sample_demo_events: list[EventRecord]) -> None:
    """Verify filtering by single or comma-separated source types."""
    # Slack only
    slack_only = filter_timeline_events(sample_demo_events, source_type="slack")
    assert all(e.source_type == SourceType.SLACK for e in slack_only)
    assert len(slack_only) > 0

    # Alerts and deployments
    multi = filter_timeline_events(
        sample_demo_events, source_type="monitoring_alert,deployment_log"
    )
    assert all(
        e.source_type in (SourceType.MONITORING_ALERT, SourceType.DEPLOYMENT_LOG) for e in multi
    )
    assert len(multi) > 0


def test_timeline_invalid_date_format_raises_error(
    sample_demo_events: list[EventRecord],
) -> None:
    """Verify invalid ISO-8601 string raises ValueError."""
    with pytest.raises(ValueError, match="Invalid ISO-8601 datetime format"):
        filter_timeline_events(sample_demo_events, start_time="invalid-date")


def test_timeline_start_after_end_raises_error(
    sample_demo_events: list[EventRecord],
) -> None:
    """Verify start_time after end_time raises ValueError."""
    with pytest.raises(ValueError, match="start_time cannot be after end_time"):
        filter_timeline_events(
            sample_demo_events,
            start_time="2026-10-30T14:30:00Z",
            end_time="2026-10-30T14:10:00Z",
        )


def test_timeline_empty_window_results(sample_demo_events: list[EventRecord]) -> None:
    """Verify a valid window with no events returns an empty list cleanly."""
    filtered = filter_timeline_events(
        sample_demo_events,
        start_time="2026-10-30T10:00:00Z",
        end_time="2026-10-30T11:00:00Z",
    )
    assert filtered == []


def test_build_timeline_response_metadata(sample_demo_events: list[EventRecord]) -> None:
    """Verify build_timeline_response outputs total_events and filtered_count."""
    resp = build_timeline_response(
        incident_id="INC-2026-042",
        all_events=sample_demo_events,
        source_type="slack",
    )
    assert resp.incident_id == "INC-2026-042"
    assert resp.total_events == 17
    assert resp.filtered_count == len(resp.events)
    assert resp.filtered_count < resp.total_events
