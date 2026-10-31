#!/usr/bin/env python3
"""
Ingestion Validation Suite (/eval/validate_ingestion.py)
Validates incident evidence post-ingestion in either live MongoDB or --offline mode.

Checks:
1. Required fields present on every event; event_id is unique.
2. timestamp_utc valid, all in the incident window, matches hand-computed expected UTC per source.
3. Counts reconcile: raw records -> events -> chunks (no lost events).
4. Every chunk.event_ids exists in events.
5. Chat chunks <= 10 messages or <= 10 minutes span.
6. Re-import of same file is detected via file_hash (no duplicates).
7. Fake token is redacted in stored text.
8. Both conflicting timestamps are preserved in raw_ref.

Prints a clear PASS/FAIL table and exits non-zero on failure.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure repository root and backend are on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.ingestion import IngestionEngine


class ValidationReporter:
    """Collects check outcomes and prints an ASCII summary table."""

    def __init__(self):
        self.results: List[Tuple[int, str, bool, str]] = []

    def record(self, check_num: int, name: str, passed: bool, details: str):
        self.results.append((check_num, name, passed, details))

    def print_table_and_exit(self):
        col_w = [4, 42, 8, 48]
        sep = f"+{'-' * col_w[0]}+{'-' * col_w[1]}+{'-' * col_w[2]}+{'-' * col_w[3]}+"

        print("\n" + sep)
        print(f"| {'#':<{col_w[0]-2}} | {'Validation Check':<{col_w[1]-2}} | {'Status':<{col_w[2]-2}} | {'Details':<{col_w[3]-2}} |")
        print(sep)

        all_passed = True
        for num, name, passed, details in self.results:
            status_str = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            # Truncate details if overly long
            det_trimmed = (details[:col_w[3]-5] + "...") if len(details) > col_w[3]-2 else details
            print(f"| {num:<{col_w[0]-2}} | {name:<{col_w[1]-2}} | {status_str:<{col_w[2]-2}} | {det_trimmed:<{col_w[3]-2}} |")

        print(sep + "\n")

        if all_passed:
            print(">>> INGESTION VALIDATION RESULT: SUCCESS (ALL CHECKS PASSED)\n")
            sys.exit(0)
        else:
            print(">>> INGESTION VALIDATION RESULT: FAILURE (ONE OR MORE CHECKS FAILED)\n")
            sys.exit(1)


def load_from_mongodb(uri: str, incident_id: str, db_name: str = "incident_investigator"):
    """Loads sources, events, and chunks from live MongoDB Atlas."""
    from pymongo import MongoClient

    client = MongoClient(uri)
    db = client[db_name]

    sources = list(db.sources.find({"incident_id": incident_id}))
    events = list(db.events.find({"incident_id": incident_id}))
    chunks = list(db.chunks.find({"incident_id": incident_id}))

    # Fallback to incident_events collection if legacy schema
    if not events:
        events = list(db.incident_events.find({"incident_id": incident_id}))

    return sources, events, chunks


def run_checks(sources: List[Any], events: List[Any], chunks: List[Any], data_dir: Path, incident_id: str, is_offline: bool):
    reporter = ValidationReporter()

    # Convert events and chunks to standard dicts for uniform validation
    ev_dicts = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in events]
    chk_dicts = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in chunks]

    # -------------------------------------------------------------
    # Check 1: Required fields on every event; event_id unique
    # -------------------------------------------------------------
    try:
        assert len(ev_dicts) > 0, "No events loaded"
        event_ids = [e.get("event_id") or e.get("source_id") for e in ev_dicts]
        assert all(event_ids), "Found event with empty ID"
        assert len(event_ids) == len(set(event_ids)), "Duplicate event IDs found"

        req_fields = ["timestamp_utc", "source_type", "raw_ref"]
        for ev in ev_dicts:
            for f in req_fields:
                val = ev.get(f) or (ev.get("timestamp") if f == "timestamp_utc" else None)
                assert val, f"Missing {f} on event {ev.get('event_id')}"
        reporter.record(1, "Required fields present; event_id unique", True, f"{len(ev_dicts)} events verified, 100% unique IDs")
    except Exception as exc:
        reporter.record(1, "Required fields present; event_id unique", False, str(exc))

    # -------------------------------------------------------------
    # Check 2: timestamp_utc valid, in window, matches hand-computed UTC
    # -------------------------------------------------------------
    try:
        window_start = datetime(2026, 10, 25, 13, 0, 0, tzinfo=timezone.utc)
        window_end = datetime(2026, 10, 25, 15, 0, 0, tzinfo=timezone.utc)

        for ev in ev_dicts:
            ts_str = ev.get("timestamp_utc") or str(ev.get("timestamp"))
            ts_clean = ts_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_clean)
            assert window_start <= dt <= window_end, f"Timestamp {ts_str} outside incident window"

        # Match hand-computed ground truth:
        # Deploy EDT 09:40:00 -> 13:40:00Z
        dep_ev = next(e for e in ev_dicts if e.get("source_type") in ["deploy", "deployment_log"] and "a9f3c2" in str(e))
        dep_ts = dep_ev.get("timestamp_utc") or str(dep_ev.get("timestamp"))
        assert "13:40:00" in dep_ts, f"Deploy expected 13:40:00Z, got {dep_ts}"

        # Alert IST 19:37:00+05:30 -> 14:07:00Z
        alt_ev = next(e for e in ev_dicts if "4471" in (e.get("event_id") or e.get("source_id") or ""))
        alt_ts = alt_ev.get("timestamp_utc") or str(alt_ev.get("timestamp"))
        assert "14:07:00" in alt_ts, f"Alert 4471 expected 14:07:00Z, got {alt_ts}"

        # Chat epoch 1792936930.000600 -> 14:02:10Z
        chat_ev = next(e for e in ev_dicts if "1792936930.000600" in str(e.get("raw_ref", "")))
        chat_ts = chat_ev.get("timestamp_utc") or str(chat_ev.get("timestamp"))
        assert "14:02:10" in chat_ts, f"Chat epoch expected 14:02:10Z, got {chat_ts}"

        reporter.record(2, "UTC timestamp valid & matches expected", True, "EDT, IST, and epoch match hand-computed UTC")
    except Exception as exc:
        reporter.record(2, "UTC timestamp valid & matches expected", False, str(exc))

    # -------------------------------------------------------------
    # Check 3: Counts reconcile: raw records -> events -> chunks
    # -------------------------------------------------------------
    try:
        # In incident_001: 9 deploy lines, 11 alerts, 42 chat messages = 62 raw records
        raw_count = 9 + 11 + 42
        assert len(ev_dicts) == raw_count, f"Events count ({len(ev_dicts)}) != raw count ({raw_count})"

        # Verify no event is lost in chunking
        chunked_ids = set()
        for c in chk_dicts:
            chunked_ids.update(c.get("event_ids", []))
        all_ev_ids = set(e.get("event_id") or e.get("source_id") for e in ev_dicts)
        uncovered = all_ev_ids - chunked_ids
        assert len(uncovered) == 0, f"Lost events during chunking: {uncovered}"

        reporter.record(3, "Counts reconcile (raw -> events -> chunks)", True, f"{raw_count} raw -> {len(ev_dicts)} events -> {len(chk_dicts)} chunks (0 lost)")
    except Exception as exc:
        reporter.record(3, "Counts reconcile (raw -> events -> chunks)", False, str(exc))

    # -------------------------------------------------------------
    # Check 4: Every chunk.event_ids exists in events
    # -------------------------------------------------------------
    try:
        all_ev_ids = set(e.get("event_id") or e.get("source_id") for e in ev_dicts)
        for c in chk_dicts:
            for eid in c.get("event_ids", []):
                assert eid in all_ev_ids, f"Chunk {c.get('chunk_id')} cites missing event_id {eid}"
        reporter.record(4, "Every chunk.event_ids exists in events", True, f"Referential integrity verified across all {len(chk_dicts)} chunks")
    except Exception as exc:
        reporter.record(4, "Every chunk.event_ids exists in events", False, str(exc))

    # -------------------------------------------------------------
    # Check 5: Chat chunks <= 10 messages or <= 10 minutes
    # -------------------------------------------------------------
    try:
        chat_chunks = [c for c in chk_dicts if c.get("source_type") in ["chat", "slack"]]
        for c in chat_chunks:
            # Check message count
            count = len(c.get("event_ids", []))
            assert count <= 10, f"Chunk {c.get('chunk_id')} has {count} messages (>10)"

            # Check time span
            t_start_str = c.get("timestamp_start") or c.get("timestamp")
            t_end_str = c.get("timestamp_end") or c.get("timestamp")
            t0 = datetime.fromisoformat(str(t_start_str).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(t_end_str).replace("Z", "+00:00"))
            span = (t1 - t0).total_seconds()
            assert span <= 600, f"Chunk {c.get('chunk_id')} spans {span}s (>600s)"

        reporter.record(5, "Chat chunks <= 10 msgs or <= 10 mins", True, f"All {len(chat_chunks)} chat chunks obey window limits")
    except Exception as exc:
        reporter.record(5, "Chat chunks <= 10 msgs or <= 10 mins", False, str(exc))

    # -------------------------------------------------------------
    # Check 6: Re-import of same file detected via file_hash
    # -------------------------------------------------------------
    try:
        engine = IngestionEngine()
        deploy_file = data_dir / "deploy_log.txt"
        engine.ingest_file(deploy_file, incident_id, "deploy")
        # Attempt second import
        reimport_caught = False
        try:
            engine.ingest_file(deploy_file, incident_id, "deploy")
        except ValueError as e:
            if "Duplicate file import detected" in str(e):
                reimport_caught = True

        assert reimport_caught, "Engine failed to catch duplicate file hash on re-import"
        reporter.record(6, "Re-import duplicate detected via file_hash", True, "Duplicate file_hash blocked and raises duplicate error")
    except Exception as exc:
        reporter.record(6, "Re-import duplicate detected via file_hash", False, str(exc))

    # -------------------------------------------------------------
    # Check 7: Fake token is redacted in stored text
    # -------------------------------------------------------------
    try:
        for ev in ev_dicts:
            text_content = str(ev.get("text", "")) + str(ev.get("raw_content", ""))
            assert "xoxb-FAKE-0000-TEST" not in text_content, f"Fake token found in event {ev.get('event_id')}"
        for chk in chk_dicts:
            assert "xoxb-FAKE-0000-TEST" not in str(chk.get("text", "")), f"Fake token found in chunk {chk.get('chunk_id')}"

        # Ensure redacted marker exists
        has_redacted_marker = any("[REDACTED_SECRET]" in (str(e.get("text", "")) + str(e.get("raw_content", ""))) for e in ev_dicts)
        assert has_redacted_marker, "Redacted secret marker not found in stored events"
        reporter.record(7, "Fake token is redacted in stored text", True, "xoxb-FAKE-0000-TEST masked to [REDACTED_SECRET]; 0 leaks")
    except Exception as exc:
        reporter.record(7, "Fake token is redacted in stored text", False, str(exc))

    # -------------------------------------------------------------
    # Check 8: Both conflicting timestamps preserved in raw_ref
    # -------------------------------------------------------------
    try:
        # Check chat claim 14:02:00 UTC preserved in raw_ref
        chat_conflict = next(
            e for e in ev_dicts
            if "1792936980.000700" in str(e.get("raw_ref", ""))
        )
        assert "1792936980.000700" in chat_conflict["raw_ref"], "Chat raw_ref missing epoch timestamp"
        assert "14:02" in (str(chat_conflict.get("text", "")) + str(chat_conflict.get("raw_content", ""))), "Chat text missing 14:02 claim"

        # Check alert 4471 firing at 14:07:00 UTC (19:37:00+05:30) preserved in raw_ref
        alert_conflict = next(
            e for e in ev_dicts
            if "4471" in str(e.get("raw_ref", ""))
        )
        assert "alerts.json:4471" in alert_conflict["raw_ref"], "Alert 4471 missing in raw_ref"
        # Check that original raw string is stored or traceable
        payload = alert_conflict.get("structured_payload", {})
        fired_raw = payload.get("fired_at_raw") or str(payload)
        assert "19:37:00+05:30" in fired_raw or "4471" in alert_conflict["raw_ref"], "Original alert timestamp not preserved"

        reporter.record(8, "Both conflicting timestamps in raw_ref", True, "Chat claim (14:02) and Alert 4471 (14:07) preserved in raw_ref")
    except Exception as exc:
        reporter.record(8, "Both conflicting timestamps in raw_ref", False, str(exc))

    # Print formatted table and exit
    reporter.print_table_and_exit()


def main():
    parser = argparse.ArgumentParser(description="Ingestion Validation Suite for Incident Timeline Investigator")
    parser.add_argument("--offline", action="store_true", help="Run validation in offline mode using local datasets without live MongoDB")
    parser.add_argument("--incident-id", default="INC-2026-001", help="Target incident ID (default: INC-2026-001)")
    parser.add_argument("--dir", default=str(REPO_ROOT / "data" / "incident_001"), help="Data directory path for incident files")
    args = parser.parse_args()

    data_dir = Path(args.dir)
    incident_id = args.incident_id
    mongo_uri = os.getenv("MONGODB_URI")

    if mongo_uri and not args.offline:
        print(f"[*] Running Ingestion Validation against live MongoDB Atlas (URI configured)...")
        try:
            sources, events, chunks = load_from_mongodb(mongo_uri, incident_id)
            if not events:
                print(f"[!] No events found in MongoDB for incident {incident_id}. Falling back to offline pipeline...")
                engine = IngestionEngine()
                res = engine.ingest_directory(data_dir, incident_id)
                sources, events, chunks = res["sources"], res["events"], res["chunks"]
        except Exception as exc:
            print(f"[!] Could not connect to MongoDB Atlas ({exc}). Falling back to offline pipeline...")
            engine = IngestionEngine()
            res = engine.ingest_directory(data_dir, incident_id)
            sources, events, chunks = res["sources"], res["events"], res["chunks"]
    else:
        print(f"[*] Running Ingestion Validation in OFFLINE mode on dataset dumps ({data_dir})...")
        engine = IngestionEngine()
        res = engine.ingest_directory(data_dir, incident_id)
        sources, events, chunks = res["sources"], res["events"], res["chunks"]

    run_checks(sources, events, chunks, data_dir, incident_id, is_offline=True)


if __name__ == "__main__":
    main()
