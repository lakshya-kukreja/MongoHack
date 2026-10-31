"""
Ingestion Service for Incident Timeline Investigator.
Parses heterogeneous sources (Chat, Alerts, Deploy logs), normalizes timestamps to UTC,
redacts sensitive credentials, chunks conversation windows, and produces canonical EventRecords.
"""

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.core.logging import logger

try:
    from app.models.event import (
        EventRecord,
        SourceType,
        format_utc_iso,
        parse_to_utc_datetime,
    )
    from app.models.schema import SourceDocument, NormalizedEvent, ChunkRecord
except ImportError:
    from backend.app.models.event import (
        EventRecord,
        SourceType,
        format_utc_iso,
        parse_to_utc_datetime,
    )
    from backend.app.models.schema import SourceDocument, NormalizedEvent, ChunkRecord

try:
    from app.services.embeddings import generate_event_embeddings, EmbeddingError
except Exception:
    generate_event_embeddings = None  # type: ignore
    EmbeddingError = Exception  # type: ignore


SECRET_REGEX = re.compile(r"xox[baprs]-[A-Za-z0-9-]+", re.IGNORECASE)


def compute_file_hash(content: str) -> str:
    """Computes SHA-256 hash of raw file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def redact_secrets(text: str) -> str:
    """Masks secret tokens (e.g. Slack tokens) to prevent credential leakage."""
    return re.sub(r"xox[baprs]-[A-Za-z0-9-]+", "[REDACTED_SECRET]", str(text))


def normalize_event_dict(
    raw: Dict[str, Any], default_incident_id: Optional[str] = None
) -> EventRecord:
    """Normalizes an arbitrary event dictionary into a validated EventRecord."""
    if not isinstance(raw, dict):
        raise ValueError("Event record must be a dictionary")

    data = dict(raw)

    # 1. Validate required source_id
    source_id = data.get("source_id")
    if not source_id or not str(source_id).strip():
        raise ValueError("Missing required field: source_id")

    # 2. Validate required incident_id
    incident_id = data.get("incident_id") or default_incident_id
    if not incident_id or not str(incident_id).strip():
        raise ValueError("Missing required field: incident_id")
    data["incident_id"] = incident_id

    # 3. Validate timestamp
    raw_ts = data.get("timestamp")
    if raw_ts is None:
        raw_ts = data.get("ts") if "ts" in data else (data.get("fired_at") or data.get("created_at"))
    if raw_ts is None or (isinstance(raw_ts, str) and not raw_ts.strip()):
        raise ValueError("Missing required timestamp")

    try:
        parsed_dt = parse_to_utc_datetime(raw_ts)
        data["timestamp"] = parsed_dt
    except Exception as exc:
        raise ValueError(f"Invalid timestamp: {raw_ts}") from exc

    # 4. Infer and normalize source_type
    raw_type = str(data.get("source_type", "")).lower()
    if raw_type in ["slack", "chat"] or "speaker" in data or "channel" in data:
        st = SourceType.SLACK
    elif raw_type in ["alert", "monitoring_alert"] or "monitor" in data or "metric" in data:
        st = SourceType.MONITORING_ALERT
    elif raw_type in ["deploy", "deployment_log"] or "deployer" in data or "version" in data:
        st = SourceType.DEPLOYMENT_LOG
    else:
        st = SourceType.SLACK
    data["source_type"] = st

    # 5. Author or actor
    actor = (
        data.get("author_or_actor")
        or data.get("speaker")
        or data.get("deployer")
        or data.get("monitor")
        or data.get("actor")
        or data.get("user")
        or "system"
    )
    data["author_or_actor"] = actor

    # 6. Channel or service
    channel_svc = (
        data.get("channel_or_service")
        or data.get("channel")
        or data.get("service")
        or "general"
    )
    data["channel_or_service"] = channel_svc

    # 7. Raw content & secret redaction
    content = (
        data.get("raw_content")
        or data.get("message")
        or data.get("text")
        or data.get("content")
        or data.get("summary")
        or ""
    )
    data["raw_content"] = redact_secrets(content)

    # 8. Summary
    if not data.get("summary"):
        data["summary"] = data["raw_content"][:120] if data["raw_content"] else f"{st.value} event"

    # 9. Structured payload capture
    core_keys = {
        "source_id", "incident_id", "timestamp", "source_type",
        "author_or_actor", "channel_or_service", "summary",
        "raw_content", "embedding_text", "embedding", "tags",
        "created_at", "structured_payload"
    }
    payload = dict(data.get("structured_payload") or {})
    for k, v in data.items():
        if k not in core_keys and k not in ["ts", "speaker", "deployer", "monitor", "channel", "service", "message", "text"]:
            payload[k] = v
    data["structured_payload"] = payload

    # 10. Canonical embedding text
    if not data.get("embedding_text"):
        src_tag = st.value.upper()
        ts_iso = format_utc_iso(data["timestamp"])
        data["embedding_text"] = f"[{src_tag}] [{ts_iso}] {channel_svc} ({actor}): {data['summary']}"

    return EventRecord.model_validate(data)


def parse_deploy_log(content: str, incident_id: str, source_id: str, filename: str) -> List[NormalizedEvent]:
    """
    Parses plain-text deploy logs in Server-Local EDT time (America/New_York, UTC-4)
    and converts timestamps to normalized UTC.
    """
    events = []
    lines = content.splitlines()
    edt_tz = timezone(timedelta(hours=-4))

    line_pattern = re.compile(
        r"^\[(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) EDT\]\s*\[(?P<lvl>\w+)\]\s*\[(?P<logger>[\w\-]+)\]\s*(?P<msg>.*)$"
    )

    idx = 1
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = line_pattern.match(line)
        if not match:
            continue

        dt_str = match.group("dt")
        logger_name = match.group("logger")
        msg = match.group("msg")

        naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        aware_dt = naive_dt.replace(tzinfo=edt_tz)
        utc_dt = aware_dt.astimezone(timezone.utc)
        utc_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        props = {}
        for part in msg.split("|"):
            if ":" in part:
                k, v = part.split(":", 1)
                props[k.strip().lower()] = v.strip()

        service = props.get("service", "deploy-service")
        actor = props.get("deployer", logger_name)
        commit = props.get("commit")

        event = NormalizedEvent(
            event_id=f"EVT-DEP-{idx:03d}",
            source_id=source_id,
            incident_id=incident_id,
            timestamp_utc=utc_iso,
            source_type="deploy",
            actor=actor,
            service=service,
            channel=None,
            text=redact_secrets(msg),
            raw_ref=f"{filename}:L{line_no}",
            structured_payload=props,
            tags=["deploy", service] + ([commit] if commit else []),
        )
        events.append(event)
        idx += 1

    return events


def parse_alerts(content: str, incident_id: str, source_id: str, filename: str) -> List[NormalizedEvent]:
    """
    Parses JSON alerts with ISO-8601 offset strings (e.g. +05:30) and converts to UTC.
    """
    records = json.loads(content)
    events = []

    for idx, alert in enumerate(records, start=1):
        fired_at = alert["fired_at"]
        dt = datetime.fromisoformat(fired_at).astimezone(timezone.utc)
        utc_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        alert_id = alert["alert_id"]
        service = alert["service"]
        severity = alert["severity"]
        error_code = alert.get("error_code", "UNKNOWN")
        message = alert["message"]

        event = NormalizedEvent(
            event_id=f"EVT-ALT-{alert_id}",
            source_id=source_id,
            incident_id=incident_id,
            timestamp_utc=utc_iso,
            source_type="alert",
            actor="datadog-monitor",
            service=service,
            channel=None,
            text=redact_secrets(message),
            raw_ref=f"{filename}:{alert_id}",
            structured_payload={
                "alert_id": alert_id,
                "severity": severity,
                "error_code": error_code,
                "fired_at_raw": fired_at,
            },
            tags=["alert", service, severity, error_code, alert_id],
        )
        events.append(event)

    return events


def parse_chat_export(content: str, incident_id: str, source_id: str, filename: str) -> List[NormalizedEvent]:
    """
    Parses Slack chat JSON with epoch seconds timestamps and converts to UTC.
    """
    records = json.loads(content)
    events = []

    for idx, msg in enumerate(records, start=1):
        ts_str = msg["ts"]
        ts_float = float(ts_str)
        dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        utc_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        user = msg.get("user", "unknown-user")
        channel = msg.get("channel", "#incidents")
        raw_text = msg.get("text", "")
        clean_text = redact_secrets(raw_text)

        payload = {
            "ts": ts_str,
            "thread_ts": msg.get("thread_ts"),
            "client_msg_id": msg.get("client_msg_id"),
        }

        event = NormalizedEvent(
            event_id=f"EVT-CHT-{idx:03d}",
            source_id=source_id,
            incident_id=incident_id,
            timestamp_utc=utc_iso,
            source_type="chat",
            actor=user,
            service="checkout-api" if "#checkout" in channel else "incidents-channel",
            channel=channel,
            text=clean_text,
            raw_ref=f"{filename}:{ts_str}",
            structured_payload=payload,
            tags=["chat", channel, user],
        )
        events.append(event)

    return events


def chunk_events(events: List[NormalizedEvent], incident_id: str) -> List[ChunkRecord]:
    """
    Groups events into retrieval chunks:
    - Deploy events: 1 chunk per event.
    - Alert events: 1 chunk per event.
    - Chat events: Grouped into conversation windows of <= 10 messages OR <= 10 minutes (600s).
    """
    chunks = []
    chunk_counter = 1

    deploy_events = [e for e in events if e.source_type == "deploy"]
    alert_events = [e for e in events if e.source_type == "alert"]
    chat_events = [e for e in events if e.source_type == "chat"]

    for ev in deploy_events:
        chunk = ChunkRecord(
            chunk_id=f"CHK-{chunk_counter:04d}",
            event_ids=[ev.event_id],
            incident_id=incident_id,
            timestamp_start=ev.timestamp_utc,
            timestamp_end=ev.timestamp_utc,
            source_type="deploy",
            service=ev.service,
            text=f"[DEPLOY] [{ev.timestamp_utc}] {ev.service} ({ev.actor}): {ev.text}",
        )
        chunks.append(chunk)
        chunk_counter += 1

    for ev in alert_events:
        chunk = ChunkRecord(
            chunk_id=f"CHK-{chunk_counter:04d}",
            event_ids=[ev.event_id],
            incident_id=incident_id,
            timestamp_start=ev.timestamp_utc,
            timestamp_end=ev.timestamp_utc,
            source_type="alert",
            service=ev.service,
            text=f"[ALERT] [{ev.timestamp_utc}] {ev.service} ({ev.actor}): {ev.text}",
        )
        chunks.append(chunk)
        chunk_counter += 1

    if chat_events:
        sorted_chat = sorted(chat_events, key=lambda x: x.timestamp_utc)
        current_group: List[NormalizedEvent] = []
        current_start_dt: Optional[datetime] = None

        for ev in sorted_chat:
            ev_dt = datetime.fromisoformat(ev.timestamp_utc.replace("Z", "+00:00"))

            if not current_group:
                current_group.append(ev)
                current_start_dt = ev_dt
                continue

            span_seconds = (ev_dt - current_start_dt).total_seconds()
            is_same_channel = (ev.channel == current_group[0].channel)

            if len(current_group) < 10 and span_seconds <= 600 and is_same_channel:
                current_group.append(ev)
            else:
                chunk_text = "\n".join(
                    f"[{m.channel}] {m.actor} ({m.timestamp_utc}): {m.text}" for m in current_group
                )
                chunks.append(
                    ChunkRecord(
                        chunk_id=f"CHK-{chunk_counter:04d}",
                        event_ids=[m.event_id for m in current_group],
                        incident_id=incident_id,
                        timestamp_start=current_group[0].timestamp_utc,
                        timestamp_end=current_group[-1].timestamp_utc,
                        source_type="chat",
                        service=current_group[0].service,
                        text=chunk_text,
                    )
                )
                chunk_counter += 1
                current_group = [ev]
                current_start_dt = ev_dt

        if current_group:
            chunk_text = "\n".join(
                f"[{m.channel}] {m.actor} ({m.timestamp_utc}): {m.text}" for m in current_group
            )
            chunks.append(
                ChunkRecord(
                    chunk_id=f"CHK-{chunk_counter:04d}",
                    event_ids=[m.event_id for m in current_group],
                    incident_id=incident_id,
                    timestamp_start=current_group[0].timestamp_utc,
                    timestamp_end=current_group[-1].timestamp_utc,
                    source_type="chat",
                    service=current_group[0].service,
                    text=chunk_text,
                )
            )
            chunk_counter += 1

    return chunks


class IngestionEngine:
    """Manages the full multi-file ingestion pipeline."""

    def __init__(self):
        self.sources: Dict[str, SourceDocument] = {}
        self.events: List[NormalizedEvent] = []
        self.chunks: List[ChunkRecord] = []

    def ingest_file(self, file_path: Path, incident_id: str, source_type: str, owner: str = "devops-team") -> Tuple[SourceDocument, List[NormalizedEvent]]:
        """Imports a single evidence file. Rejects duplicates matching an existing file_hash."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        file_hash = compute_file_hash(content)
        if file_hash in self.sources:
            existing = self.sources[file_hash]
            raise ValueError(f"Duplicate file import detected! File '{file_path.name}' matches hash of already imported source '{existing.filename}' (hash: {file_hash}).")

        filename = file_path.name
        source_id = f"SRC-{incident_id}-{len(self.sources) + 1:02d}"

        if source_type == "chat":
            new_events = parse_chat_export(content, incident_id, source_id, filename)
        elif source_type == "alert":
            new_events = parse_alerts(content, incident_id, source_id, filename)
        elif source_type == "deploy":
            new_events = parse_deploy_log(content, incident_id, source_id, filename)
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

        source_doc = SourceDocument(
            source_id=source_id,
            incident_id=incident_id,
            owner=owner,
            source_type=source_type,
            filename=filename,
            file_hash=file_hash,
            imported_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            record_count=len(new_events),
        )

        self.sources[file_hash] = source_doc
        self.events.extend(new_events)
        return source_doc, new_events

    def ingest_directory(self, dir_path: Path, incident_id: str, owner: str = "devops-team") -> Dict[str, Any]:
        """Ingests chat_export.json, alerts.json, and deploy_log.txt from a directory."""
        chat_path = dir_path / "chat_export.json"
        alerts_path = dir_path / "alerts.json"
        deploy_path = dir_path / "deploy_log.txt"

        imported_sources = []
        if deploy_path.exists():
            src, _ = self.ingest_file(deploy_path, incident_id, "deploy", owner)
            imported_sources.append(src)
        if alerts_path.exists():
            src, _ = self.ingest_file(alerts_path, incident_id, "alert", owner)
            imported_sources.append(src)
        if chat_path.exists():
            src, _ = self.ingest_file(chat_path, incident_id, "chat", owner)
            imported_sources.append(src)

        # Build chunks across all normalized events
        self.chunks = chunk_events(self.events, incident_id)

        return {
            "incident_id": incident_id,
            "sources": imported_sources,
            "events_count": len(self.events),
            "chunks_count": len(self.chunks),
            "events": self.events,
            "chunks": self.chunks,
        }


def parse_incident_data(
    data_input: Union[str, Path, list[dict[str, Any]], dict[str, Any]],
    default_incident_id: Optional[str] = None,
    attach_embeddings: bool = False,
) -> list[EventRecord]:
    """Parse JSON file, JSON string, JSONL, or python dicts into validated EventRecords.

    Ensures chronological stability and uniqueness of source_id within an incident.

    Args:
        data_input: File path, string content, raw list of dicts, or dictionary with 'events'.
        default_incident_id: Incident ID fallback.
        attach_embeddings: If True, attempt to generate embeddings for events.

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

    # Optionally attach embeddings if requested
    if attach_embeddings and generate_event_embeddings is not None and normalized_records:
        try:
            embeddings = generate_event_embeddings(normalized_records)
            for event, emb in zip(normalized_records, embeddings):
                event.embedding = emb
        except EmbeddingError as exc:
            logger.warning(f"Failed to attach embeddings during ingestion: {exc}")
        except Exception as exc:
            logger.warning(f"Unexpected error attaching embeddings: {exc}")

    return normalized_records
