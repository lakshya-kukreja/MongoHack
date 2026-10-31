"""
Canonical Data Model for Incident Timeline Investigator.
Defines Pydantic models for sources, normalized events, and retrieval chunks.
Conforms to spec.md and AGENTS.md.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    """Represents an imported raw evidence file."""
    id: Optional[str] = Field(default=None, alias="_id")
    source_id: str
    incident_id: str
    owner: str = "devops-team"
    source_type: str  # "chat" | "alert" | "deploy"
    filename: str
    file_hash: str  # SHA-256 hash of original file content
    imported_at: str  # ISO-8601 UTC
    record_count: int


class NormalizedEvent(BaseModel):
    """Normalized, time-sortable record of each message, alert, or deploy."""
    event_id: str
    source_id: str
    incident_id: str
    timestamp_utc: str  # ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ)
    source_type: str  # "chat" | "alert" | "deploy"
    actor: str
    service: str
    channel: Optional[str] = None
    text: str
    raw_ref: str  # File plus line or message timestamp/id
    structured_payload: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class ChunkRecord(BaseModel):
    """Retrieval unit with vector embedding citing back to event_ids."""
    chunk_id: str
    event_ids: List[str]
    incident_id: str
    timestamp_start: str  # ISO-8601 UTC
    timestamp_end: str    # ISO-8601 UTC
    source_type: str
    service: str
    text: str
    embedding: Optional[List[float]] = None
