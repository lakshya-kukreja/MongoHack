"""Tests for incident data ingestion and normalization."""

from datetime import datetime, timezone
import pytest
from app.models.event import EventRecord, SourceType
from app.services.ingestion import normalize_event_dict, parse_incident_data


def test_parse_demo_dataset(sample_demo_events: list[EventRecord]) -> None:
    """Verify the realistic demo dataset parses completely into EventRecords."""
    assert len(sample_demo_events) == 17
    incident_ids = {ev.incident_id for ev in sample_demo_events}
    assert incident_ids == {"INC-2026-042"}

    # Verify source type breakdown
    source_types = {ev.source_type for ev in sample_demo_events}
    assert SourceType.SLACK in source_types
    assert SourceType.MONITORING_ALERT in source_types
    assert SourceType.DEPLOYMENT_LOG in source_types


def test_normalize_raw_slack_event() -> None:
    """Verify raw Slack message dictionary normalizes cleanly."""
    raw = {
        "speaker": "alice.dev",
        "channel": "#incidents-prod",
        "text": "Investigating checkout latency spike.",
        "ts": "2026-10-30T14:04:10Z",
        "source_id": "SLACK-301",
        "incident_id": "INC-2026-042",
    }
    event = normalize_event_dict(raw)
    assert event.source_id == "SLACK-301"
    assert event.incident_id == "INC-2026-042"
    assert event.author_or_actor == "alice.dev"
    assert event.channel_or_service == "#incidents-prod"
    assert event.source_type == SourceType.SLACK
    assert event.raw_content == "Investigating checkout latency spike."
    assert "[SLACK]" in event.embedding_text


def test_normalize_raw_alert_event() -> None:
    """Verify raw monitoring alert normalizes and captures structured payload."""
    raw = {
        "source_id": "ALERT-201",
        "incident_id": "INC-2026-042",
        "timestamp": "2026-10-30T14:02:00Z",
        "monitor": "datadog-monitor",
        "service": "checkout-service",
        "metric": "p99_latency",
        "threshold": 2000,
        "measured_value": 2840,
        "severity": "CRITICAL",
        "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
    }
    event = normalize_event_dict(raw)
    assert event.source_id == "ALERT-201"
    assert event.source_type == SourceType.MONITORING_ALERT
    assert event.author_or_actor == "datadog-monitor"
    assert event.channel_or_service == "checkout-service"
    assert event.structured_payload["metric"] == "p99_latency"
    assert event.structured_payload["measured_value"] == 2840


def test_normalize_raw_deployment_event() -> None:
    """Verify raw deployment log normalizes properly."""
    raw = {
        "source_id": "DEPLOY-101",
        "incident_id": "INC-2026-042",
        "timestamp": "2026-10-30T13:45:00Z",
        "deployer": "marcus.eng",
        "service": "checkout-service",
        "version": "v2.4.1",
        "commit": "a1f9c8d",
        "message": "Deployment of checkout-service v2.4.1",
    }
    event = normalize_event_dict(raw)
    assert event.source_id == "DEPLOY-101"
    assert event.source_type == SourceType.DEPLOYMENT_LOG
    assert event.author_or_actor == "marcus.eng"
    assert event.channel_or_service == "checkout-service"
    assert event.structured_payload["version"] == "v2.4.1"


def test_timestamp_timezone_normalization() -> None:
    """Verify non-UTC offsets are converted to canonical UTC."""
    # 10:00:00 -04:00 is 14:00:00 UTC
    raw = {
        "source_id": "SLACK-100",
        "incident_id": "INC-1",
        "timestamp": "2026-10-30T10:00:00-04:00",
        "speaker": "bob",
        "channel": "#ops",
        "message": "Hello",
    }
    event = normalize_event_dict(raw)
    assert event.timestamp == datetime(2026, 10, 30, 14, 0, 0, tzinfo=timezone.utc)


def test_epoch_timestamp_parsing() -> None:
    """Verify unix timestamps (e.g. from Slack ts) are parsed to UTC datetime."""
    epoch_ts = 1793369100.0  # Approx 2026-10-30T14:05:00Z
    raw = {
        "source_id": "SLACK-101",
        "incident_id": "INC-1",
        "ts": epoch_ts,
        "speaker": "bob",
        "channel": "#ops",
        "message": "Hello",
    }
    event = normalize_event_dict(raw)
    assert event.timestamp.tzinfo == timezone.utc


def test_missing_timestamp_raises_error() -> None:
    """Verify missing timestamp raises ValueError."""
    raw = {
        "source_id": "SLACK-100",
        "incident_id": "INC-1",
        "speaker": "bob",
        "message": "Missing timestamp",
    }
    with pytest.raises(ValueError, match="Missing required timestamp"):
        normalize_event_dict(raw)


def test_invalid_timestamp_raises_error() -> None:
    """Verify malformed timestamp string raises ValueError."""
    raw = {
        "source_id": "SLACK-100",
        "incident_id": "INC-1",
        "timestamp": "invalid-timestamp-string",
        "speaker": "bob",
        "message": "Malformed timestamp",
    }
    with pytest.raises(ValueError, match="Invalid timestamp"):
        normalize_event_dict(raw)


def test_missing_source_id_raises_error() -> None:
    """Verify missing source_id raises ValueError."""
    raw = {
        "incident_id": "INC-1",
        "timestamp": "2026-10-30T14:00:00Z",
        "message": "No source id",
    }
    with pytest.raises(ValueError, match="Missing required field: source_id"):
        normalize_event_dict(raw)


def test_missing_incident_id_raises_error() -> None:
    """Verify missing incident_id raises ValueError when no default is provided."""
    raw = {
        "source_id": "ALERT-1",
        "timestamp": "2026-10-30T14:00:00Z",
        "message": "No incident id",
    }
    with pytest.raises(ValueError, match="Missing required field: incident_id"):
        normalize_event_dict(raw)


def test_duplicate_source_id_in_batch_raises_error() -> None:
    """Verify batches with duplicated source IDs in the same incident are rejected."""
    batch = [
        {
            "source_id": "ALERT-201",
            "incident_id": "INC-1",
            "timestamp": "2026-10-30T14:00:00Z",
            "message": "First alert",
        },
        {
            "source_id": "ALERT-201",
            "incident_id": "INC-1",
            "timestamp": "2026-10-30T14:05:00Z",
            "message": "Duplicate alert",
        },
    ]
    with pytest.raises(ValueError, match="Duplicate source_id 'ALERT-201'"):
        parse_incident_data(batch)
