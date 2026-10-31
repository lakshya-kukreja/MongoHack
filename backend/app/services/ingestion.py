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


SECRET_REGEX = re.compile(r"xox[baprs]-[A-Za-z0-9-]+", re.IGNORECASE)


def compute_file_hash(content: str) -> str:
    """Computes SHA-256 hash of raw file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def redact_secrets(text: str) -> str:
    """Masks secret tokens (e.g. Slack tokens) to prevent credential leakage."""
    return re.sub(r"xox[baprs]-[A-Za-z0-9-]+", "[REDACTED_SECRET]", text)


def normalize_event_dict(raw: Dict[str, Any]) -> EventRecord:
    """Normalizes an arbitrary event dictionary into a validated EventRecord."""
    data = dict(raw)
    
    # Normalize source_type
    raw_type = str(data.get("source_type", "")).lower()
    if "slack" in raw_type or "chat" in raw_type:
        st = SourceType.SLACK
    elif "alert" in raw_type:
        st = SourceType.MONITORING_ALERT
    elif "deploy" in raw_type:
        st = SourceType.DEPLOYMENT_LOG
    else:
        st = SourceType.SLACK
    data["source_type"] = st

    # Redact raw content
    if "raw_content" in data and isinstance(data["raw_content"], str):
        data["raw_content"] = redact_secrets(data["raw_content"])
    elif "text" in data and isinstance(data["text"], str):
        data["raw_content"] = redact_secrets(data["text"])
    elif "message" in data and isinstance(data["message"], str):
        data["raw_content"] = redact_secrets(data["message"])

    # Fallback summary
    if not data.get("summary"):
        data["summary"] = data.get("raw_content", "")[:120]

    return EventRecord.model_validate(data)


def parse_incident_data(data: Union[List[Dict[str, Any]], str]) -> List[EventRecord]:
    """Parses a list of event dictionaries or a JSON string into validated EventRecords."""
    if isinstance(data, str):
        raw_list = json.loads(data)
    else:
        raw_list = data

    return [normalize_event_dict(item) for item in raw_list]


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

        # Convert EDT to UTC
        naive_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        aware_dt = naive_dt.replace(tzinfo=edt_tz)
        utc_dt = aware_dt.astimezone(timezone.utc)
        utc_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Extract structured properties
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

    # Separate events by source type
    deploy_events = [e for e in events if e.source_type == "deploy"]
    alert_events = [e for e in events if e.source_type == "alert"]
    chat_events = [e for e in events if e.source_type == "chat"]

    # 1. Deploy chunks (1:1)
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

    # 2. Alert chunks (1:1)
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

    # 3. Chat chunks (Conversation windows: <= 10 messages OR <= 10 minutes span)
    if chat_events:
        # Sort chat events chronologically
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

            # Check window boundaries: max 10 messages OR max 10 minutes (600 seconds)
            if len(current_group) < 10 and span_seconds <= 600 and is_same_channel:
                current_group.append(ev)
            else:
                # Flush existing chunk
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

        # Flush final chat chunk
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
    """Manages document importing, deduplication via file_hash, normalization, and chunking."""

    def __init__(self):
        self.sources: Dict[str, SourceDocument] = {}  # keyed by file_hash
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
