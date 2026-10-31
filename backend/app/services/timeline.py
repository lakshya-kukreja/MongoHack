"""Deterministic timeline sorting, windowing, and filtering engine."""

from datetime import datetime
from typing import Optional, Union
from app.models.event import (
    EventRecord,
    SourceType,
    TimelineResponse,
    parse_to_utc_datetime,
)


def sort_events_chronologically(events: list[EventRecord]) -> list[EventRecord]:
    """Deterministically sort events strictly by timestamp ascending.

    Secondary sort key is source_id to guarantee deterministic ordering
    when two events share the exact same timestamp.

    Args:
        events: List of EventRecord models.

    Returns:
        Sorted list of EventRecord models.
    """
    return sorted(events, key=lambda ev: (ev.timestamp, ev.source_id))


def parse_filter_datetime(dt_input: Optional[Union[datetime, str]], field_name: str) -> Optional[datetime]:
    """Parse and validate filter datetimes."""
    if dt_input is None:
        return None
    if isinstance(dt_input, datetime):
        return parse_to_utc_datetime(dt_input)
    if isinstance(dt_input, str):
        cleaned = dt_input.strip()
        if not cleaned:
            return None
        try:
            return parse_to_utc_datetime(cleaned)
        except Exception as exc:
            raise ValueError(
                f"Invalid ISO-8601 datetime format for {field_name}: {dt_input}"
            ) from exc
    raise ValueError(f"Invalid type for {field_name}: {type(dt_input).__name__}")


def parse_source_types_filter(
    source_type_param: Optional[Union[list[str], str]]
) -> Optional[set[str]]:
    """Parse source_type query param into a set of normalized source type strings."""
    if not source_type_param:
        return None

    types_set: set[str] = set()
    if isinstance(source_type_param, str):
        parts = source_type_param.split(",")
    else:
        parts = source_type_param

    valid_types = {t.value for t in SourceType}
    for item in parts:
        cleaned = item.strip().lower()
        if cleaned:
            if cleaned not in valid_types:
                raise ValueError(
                    f"Invalid source_type '{cleaned}'. Must be one of: {', '.join(sorted(valid_types))}"
                )
            types_set.add(cleaned)

    return types_set if types_set else None


def filter_timeline_events(
    events: list[EventRecord],
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    source_type: Optional[Union[list[str], str]] = None,
) -> list[EventRecord]:
    """Filter and sort events deterministically by time window and source type.

    Both time window boundaries are inclusive:
    event.timestamp >= start_time AND event.timestamp <= end_time.

    Args:
        events: All candidate records for the incident.
        start_time: Earliest timestamp (inclusive).
        end_time: Latest timestamp (inclusive).
        source_type: Comma-separated string or list of source types to include.

    Returns:
        Filtered list of events in ascending chronological order.

    Raises:
        ValueError: If timestamps or source types are malformed or start_time > end_time.
    """
    parsed_start = parse_filter_datetime(start_time, "start_time")
    parsed_end = parse_filter_datetime(end_time, "end_time")

    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise ValueError("start_time cannot be after end_time")

    allowed_sources = parse_source_types_filter(source_type)

    filtered: list[EventRecord] = []
    for ev in events:
        if parsed_start and ev.timestamp < parsed_start:
            continue
        if parsed_end and ev.timestamp > parsed_end:
            continue
        if allowed_sources and ev.source_type.value not in allowed_sources:
            continue
        filtered.append(ev)

    return sort_events_chronologically(filtered)


def build_timeline_response(
    incident_id: str,
    all_events: list[EventRecord],
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    source_type: Optional[Union[list[str], str]] = None,
) -> TimelineResponse:
    """Construct a TimelineResponse adhering to spec.md contract."""
    filtered = filter_timeline_events(
        events=all_events,
        start_time=start_time,
        end_time=end_time,
        source_type=source_type,
    )

    return TimelineResponse(
        incident_id=incident_id,
        total_events=len(all_events),
        filtered_count=len(filtered),
        events=filtered,
    )
