"""Data ingestion and normalization for heterogeneous incident sources."""

import json
from pathlib import Path
from typing import Any, Optional, Union
from app.models.event import (
    EventRecord,
    SourceType,
    format_utc_iso,
    parse_to_utc_datetime,
)


def _infer_source_type(raw: dict[str, Any]) -> SourceType:
    """Infer the SourceType from raw dictionary keys and values."""
    if "source_type" in raw and raw["source_type"]:
        st = str(raw["source_type"]).lower().strip()
        if st in ("slack", "chat"):
            return SourceType.SLACK
        if st in ("monitoring_alert", "alert", "monitoring"):
            return SourceType.MONITORING_ALERT
        if st in ("deployment_log", "deployment", "deploy"):
            return SourceType.DEPLOYMENT_LOG

    source_id = str(raw.get("source_id", "")).upper()
    if source_id.startswith("SLACK"):
        return SourceType.SLACK
    if source_id.startswith("ALERT"):
        return SourceType.MONITORING_ALERT
    if source_id.startswith("DEPLOY"):
        return SourceType.DEPLOYMENT_LOG

    if any(k in raw for k in ("metric", "metric_name", "threshold", "severity")):
        return SourceType.MONITORING_ALERT
    if any(k in raw for k in ("commit", "deployer", "version", "cluster")):
        return SourceType.DEPLOYMENT_LOG
    if any(k in raw for k in ("speaker", "channel")):
        return SourceType.SLACK

    return SourceType.SLACK


def _build_embedding_text(
    source_type: SourceType,
    iso_timestamp: str,
    channel_or_service: str,
    author_or_actor: str,
    content: str,
) -> str:
    """Build canonical embedding text representation for vector indexing."""
    type_tag_map = {
        SourceType.SLACK: "SLACK",
        SourceType.MONITORING_ALERT: "ALERT",
        SourceType.DEPLOYMENT_LOG: "DEPLOYMENT",
    }
    tag = type_tag_map.get(source_type, "EVENT")
    return f"[{tag}] [{iso_timestamp}] {channel_or_service} ({author_or_actor}): {content}"


def normalize_event_dict(
    raw: dict[str, Any], default_incident_id: Optional[str] = None
) -> EventRecord:
    """Normalize a raw dictionary from any heterogeneous source into an EventRecord.

    Args:
        raw: Raw dictionary representing an event from Slack, Alert, or Deployment.
        default_incident_id: Fallback incident ID if not in raw record.

    Returns:
        Validated canonical EventRecord instance.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Event record must be a JSON object/dict, got {type(raw).__name__}")

    # Incident ID
    incident_id = raw.get("incident_id") or default_incident_id
    if not incident_id or not str(incident_id).strip():
        raise ValueError("Missing required field: incident_id")
    incident_id = str(incident_id).strip()

    # Source ID
    source_id = raw.get("source_id") or raw.get("id") or raw.get("event_id")
    if not source_id or not str(source_id).strip():
        raise ValueError("Missing required field: source_id")
    source_id = str(source_id).strip()

    # Timestamp
    raw_timestamp = (
        raw.get("timestamp")
        or raw.get("ts")
        or raw.get("created_at")
        or raw.get("time")
    )
    if raw_timestamp is None:
        raise ValueError(f"Missing required timestamp in record '{source_id}'")
    try:
        parsed_dt = parse_to_utc_datetime(raw_timestamp)
    except Exception as exc:
        raise ValueError(f"Invalid timestamp in record '{source_id}': {exc}") from exc

    # Source Type
    source_type = _infer_source_type(raw)

    # Actor / Author
    author_or_actor = (
        raw.get("author_or_actor")
        or raw.get("speaker")
        or raw.get("author")
        or raw.get("user")
        or raw.get("deployer")
        or raw.get("actor")
        or raw.get("monitor")
    )
    if not author_or_actor or not str(author_or_actor).strip():
        if source_type == SourceType.MONITORING_ALERT:
            author_or_actor = "monitoring-system"
        elif source_type == SourceType.DEPLOYMENT_LOG:
            author_or_actor = "ci-cd-bot"
        else:
            author_or_actor = "system"
    author_or_actor = str(author_or_actor).strip()

    # Channel / Service
    channel_or_service = (
        raw.get("channel_or_service")
        or raw.get("channel")
        or raw.get("service")
        or raw.get("repo")
    )
    if not channel_or_service or not str(channel_or_service).strip():
        channel_or_service = "general"
    channel_or_service = str(channel_or_service).strip()

    # Raw content & summary
    raw_content = (
        raw.get("raw_content")
        or raw.get("text")
        or raw.get("message")
        or raw.get("description")
        or raw.get("content")
    )
    if not raw_content or not str(raw_content).strip():
        summary_val = raw.get("summary")
        if summary_val and str(summary_val).strip():
            raw_content = str(summary_val).strip()
        else:
            raise ValueError(f"Missing content or message in record '{source_id}'")
    raw_content = str(raw_content).strip()

    summary = raw.get("summary")
    if not summary or not str(summary).strip():
        # First 120 chars as summary
        summary = raw_content[:120].strip()
    summary = str(summary).strip()

    # Structured payload
    payload = raw.get("structured_payload")
    if payload is None or not isinstance(payload, dict):
        payload = {}
        # Collect any specialized attributes
        for k in (
            "metric",
            "metric_name",
            "threshold",
            "value",
            "measured_value",
            "severity",
            "environment",
            "cluster",
            "version",
            "commit",
            "deployer",
            "channel",
            "endpoint",
        ):
            if k in raw and raw[k] is not None:
                payload[k] = raw[k]

    # Embedding text
    embedding_text = raw.get("embedding_text")
    if not embedding_text or not str(embedding_text).strip():
        iso_str = format_utc_iso(parsed_dt) or ""
        embedding_text = _build_embedding_text(
            source_type=source_type,
            iso_timestamp=iso_str,
            channel_or_service=channel_or_service,
            author_or_actor=author_or_actor,
            content=raw_content,
        )

    # Tags
    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    else:
        tags = [str(t) for t in tags if str(t).strip()]

    return EventRecord(
        source_id=source_id,
        incident_id=incident_id,
        timestamp=parsed_dt,
        source_type=source_type,
        author_or_actor=author_or_actor,
        channel_or_service=channel_or_service,
        summary=summary,
        raw_content=raw_content,
        structured_payload=payload,
        embedding_text=str(embedding_text).strip(),
        embedding=raw.get("embedding"),
        tags=tags,
    )


def parse_incident_data(
    data_input: Union[str, Path, list[dict[str, Any]], dict[str, Any]],
    default_incident_id: Optional[str] = None,
) -> list[EventRecord]:
    """Parse JSON file, JSON string, JSONL, or python dicts into validated EventRecords.

    Ensures chronological stability and uniqueness of source_id within an incident.

    Args:
        data_input: File path, string content, raw list of dicts, or dictionary with 'events'.
        default_incident_id: Incident ID fallback.

    Returns:
        List of validated canonical EventRecords.

    Raises:
        ValueError: On parsing errors or duplicate source IDs.
    """
    raw_records: list[dict[str, Any]] = []

    if isinstance(data_input, Path) or (
        isinstance(data_input, str)
        and (data_input.endswith(".json") or data_input.endswith(".jsonl"))
    ):
        path = Path(str(data_input))
        if not path.exists():
            raise FileNotFoundError(f"Incident data file not found: {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        if path.suffix == ".jsonl":
            for line_no, line in enumerate(content.splitlines(), start=1):
                line = line.strip()
                if line:
                    try:
                        raw_records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
        else:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    raw_records = parsed
                elif isinstance(parsed, dict) and "events" in parsed:
                    default_incident_id = parsed.get("incident_id") or default_incident_id
                    raw_records = parsed["events"]
                elif isinstance(parsed, dict):
                    raw_records = [parsed]
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON file {path}: {exc}") from exc

    elif isinstance(data_input, str):
        content = data_input.strip()
        if not content:
            return []
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                raw_records = parsed
            elif isinstance(parsed, dict) and "events" in parsed:
                default_incident_id = parsed.get("incident_id") or default_incident_id
                raw_records = parsed["events"]
            elif isinstance(parsed, dict):
                raw_records = [parsed]
        except json.JSONDecodeError:
            # Try parsing as JSONL
            for line_no, line in enumerate(content.splitlines(), start=1):
                line = line.strip()
                if line:
                    try:
                        raw_records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON/JSONL at line {line_no}: {exc}") from exc

    elif isinstance(data_input, list):
        raw_records = data_input

    elif isinstance(data_input, dict):
        if "events" in data_input and isinstance(data_input["events"], list):
            default_incident_id = data_input.get("incident_id") or default_incident_id
            raw_records = data_input["events"]
        else:
            raw_records = [data_input]

    else:
        raise ValueError(f"Unsupported data input type: {type(data_input).__name__}")

    # Normalize each record
    normalized_records: list[EventRecord] = []
    seen_ids: set[tuple[str, str]] = set()

    for rec in raw_records:
        norm = normalize_event_dict(rec, default_incident_id=default_incident_id)
        key = (norm.incident_id, norm.source_id)
        if key in seen_ids:
            raise ValueError(
                f"Duplicate source_id '{norm.source_id}' in incident '{norm.incident_id}'"
            )
        seen_ids.add(key)
        normalized_records.append(norm)

    return normalized_records
