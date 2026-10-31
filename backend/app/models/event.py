"""Incident event and API models for Incident Timeline Investigator."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from dateutil import parser as dt_parser
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class SourceType(str, Enum):
    """Supported incident evidence sources."""

    SLACK = "slack"
    MONITORING_ALERT = "monitoring_alert"
    DEPLOYMENT_LOG = "deployment_log"


def parse_to_utc_datetime(value: Any) -> datetime:
    """Parse various datetime representations into a timezone-aware UTC datetime.

    Args:
        value: ISO string, unix timestamp, or datetime instance.

    Returns:
        Timezone-aware datetime in UTC.

    Raises:
        ValueError: If value cannot be parsed as a valid datetime.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Timestamp string cannot be empty")
        try:
            # First attempt standard ISO-8601 parsing
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            try:
                parsed = dt_parser.isoparse(cleaned)
            except Exception as exc:
                raise ValueError(f"Invalid ISO-8601 datetime format: {cleaned}") from exc

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    raise ValueError(f"Unsupported timestamp type: {type(value).__name__}")


def format_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as canonical ISO-8601 UTC string ending with 'Z'."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class EventRecord(BaseModel):
    """Canonical incident evidence record."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    source_id: str = Field(..., min_length=1, description="Unique source event identifier")
    incident_id: str = Field(..., min_length=1, description="Incident identifier")
    timestamp: datetime = Field(..., description="UTC ISO-8601 event timestamp")
    source_type: SourceType = Field(..., description="Type of evidence source")
    author_or_actor: str = Field(..., min_length=1, description="Actor, bot, or service name")
    channel_or_service: str = Field(..., min_length=1, description="Service, channel, or repository name")
    summary: str = Field(..., min_length=1, description="Short summary for quick timeline display")
    raw_content: str = Field(..., min_length=1, description="Full unaltered content")
    structured_payload: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary structured metadata"
    )
    embedding_text: str = Field(
        default="", description="Canonical formatted text used for vector embeddings"
    )
    embedding: Optional[list[float]] = Field(
        default=None, description="Vector embedding values if generated"
    )
    tags: list[str] = Field(default_factory=list, description="Categorical tags for filtering")
    created_at: Optional[datetime] = Field(
        default=None, description="Ingestion timestamp in UTC"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        return parse_to_utc_datetime(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, v: Any) -> Optional[datetime]:
        if v is None:
            return datetime.now(timezone.utc)
        return parse_to_utc_datetime(v)

    @field_serializer("timestamp", "created_at", when_used="json")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return format_utc_iso(v)


class TimelineResponse(BaseModel):
    """Deterministic chronological timeline response."""

    incident_id: str
    total_events: int
    filtered_count: int
    events: list[EventRecord]


class IncidentSummary(BaseModel):
    """Summary overview of an incident."""

    incident_id: str
    title: str
    event_count: int
    start_time: str
    end_time: str
    services_involved: list[str]


class IngestRequest(BaseModel):
    """Request payload for ingesting incident events."""

    incident_id: str = Field(..., min_length=1)
    events: list[dict[str, Any]] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    """Response payload for incident ingestion."""

    incident_id: str
    ingested_count: int
    status: str = "success"


class HealthResponse(BaseModel):
    """API health status response."""

    status: str
    database: str
    version: str = "1.0.0"
