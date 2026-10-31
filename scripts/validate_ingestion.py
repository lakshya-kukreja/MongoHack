"""
Ingestion Validation Suite (validate_ingestion.py)
Validates the outputs of Person 1's Ingestion Pipeline across the 8 required checks:

1. Every event has event_id, timestamp_utc, source_type, and raw_ref, and event IDs are unique.
2. UTC conversion matches hand-computed values for each source format.
3. Counts reconcile: raw records -> events -> chunks, with zero events lost.
4. Every chunk.event_ids entry exists in events.
5. Chat chunks respect the limit (<=10 messages or <=10 minutes).
6. Re-importing the same file is caught by file_hash.
7. The fake token is redacted in stored text.
8. All events fall inside the incident window, and the conflicting timestamps are both preserved.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add repository root and backend to path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.ingestion import IngestionEngine


def run_ingestion_validation():
    print("\n=======================================================")
    print("  RUNNING VALIDATION SUITE: INGESTION PIPELINE")
    print("=======================================================\n")

    data_dir = REPO_ROOT / "data" / "incident_001"
    incident_id = "INC-2026-001"

    # Execute ingestion
    engine = IngestionEngine()
    result = engine.ingest_directory(data_dir, incident_id=incident_id)

    sources = result["sources"]
    events = result["events"]
    chunks = result["chunks"]

    # -------------------------------------------------------------
    # Check 1: Mandatory fields & Unique Event IDs
    # -------------------------------------------------------------
    print("[RUNNING] Check 1: Mandatory fields & event ID uniqueness...")
    assert len(events) > 0, "No events normalized"
    event_ids = [e.event_id for e in events]
    assert len(event_ids) == len(set(event_ids)), "Duplicate event_id detected!"

    for ev in events:
        assert ev.event_id, f"Empty event_id in event: {ev}"
        assert ev.timestamp_utc, f"Empty timestamp_utc in event: {ev.event_id}"
        assert ev.timestamp_utc.endswith("Z"), f"Timestamp not UTC (Z suffix missing): {ev.timestamp_utc}"
        assert ev.source_type in ["chat", "alert", "deploy"], f"Invalid source_type: {ev.source_type}"
        assert ev.raw_ref, f"Empty raw_ref in event: {ev.event_id}"
    print(f"[PASS] Check 1: All {len(events)} events have unique IDs and valid mandatory fields.")

    # -------------------------------------------------------------
    # Check 2: UTC Conversion matches hand-computed ground truth
    # -------------------------------------------------------------
    print("[RUNNING] Check 2: UTC conversion matches hand-computed values...")
    # Hand-computed 1: Deploy log [2026-10-25 09:40:00 EDT] -> 13:40:00Z
    deploy_ev = next(e for e in events if e.source_type == "deploy" and "a9f3c2" in e.text)
    assert deploy_ev.timestamp_utc == "2026-10-25T13:40:00Z", f"Deploy UTC mismatch: {deploy_ev.timestamp_utc}"

    # Hand-computed 2: Alert 4471 2026-10-25T19:37:00+05:30 -> 14:07:00Z
    alert_ev = next(e for e in events if e.event_id == "EVT-ALT-4471")
    assert alert_ev.timestamp_utc == "2026-10-25T14:07:00Z", f"Alert 4471 UTC mismatch: {alert_ev.timestamp_utc}"

    # Hand-computed 3: Chat ts 1792936930.000600 -> 14:02:10Z
    chat_ev = next(e for e in events if e.raw_ref.endswith("1792936930.000600"))
    assert chat_ev.timestamp_utc == "2026-10-25T14:02:10Z", f"Chat epoch UTC mismatch: {chat_ev.timestamp_utc}"
    print("[PASS] Check 2: UTC conversion for Server EDT, Alert ISO offset (+05:30), and Chat epoch seconds match hand-computed values exactly.")

    # -------------------------------------------------------------
    # Check 3: Counts reconcile (raw records -> events -> chunks)
    # -------------------------------------------------------------
    print("[RUNNING] Check 3: Reconciling raw records -> events -> chunks with zero event loss...")
    # Count raw records:
    # 9 deploy lines (excluding comments/blank)
    # 11 alert records
    # 42 chat messages
    # Total raw = 62
    expected_raw_count = 9 + 11 + 42
    assert len(events) == expected_raw_count, f"Event count ({len(events)}) != expected raw count ({expected_raw_count})"

    # Ensure EVERY event ID appears in at least one chunk
    all_chunked_event_ids = set()
    for chk in chunks:
        all_chunked_event_ids.update(chk.event_ids)

    missing_events = set(event_ids) - all_chunked_event_ids
    assert len(missing_events) == 0, f"Events lost during chunking! Missing: {missing_events}"
    print(f"[PASS] Check 3: Counts reconciled: 62 raw records -> 62 normalized events -> {len(chunks)} chunks. Zero events lost.")

    # -------------------------------------------------------------
    # Check 4: Every chunk.event_ids entry exists in events
    # -------------------------------------------------------------
    print("[RUNNING] Check 4: Verifying chunk.event_ids referential integrity...")
    events_set = set(event_ids)
    for chk in chunks:
        for eid in chk.event_ids:
            assert eid in events_set, f"Orphaned event_id {eid} in chunk {chk.chunk_id}"
    print(f"[PASS] Check 4: All event references in all {len(chunks)} chunks exist in normalized events.")

    # -------------------------------------------------------------
    # Check 5: Chat chunks respect <=10 messages OR <=10 minutes limit
    # -------------------------------------------------------------
    print("[RUNNING] Check 5: Verifying conversation window limits...")
    chat_chunks = [c for c in chunks if c.source_type == "chat"]
    for chk in chat_chunks:
        # Message count limit
        msg_count = len(chk.event_ids)
        assert msg_count <= 10, f"Chat chunk {chk.chunk_id} exceeds 10 messages (has {msg_count})"

        # Time span limit (<= 600 seconds)
        dt_start = datetime.fromisoformat(chk.timestamp_start.replace("Z", "+00:00"))
        dt_end = datetime.fromisoformat(chk.timestamp_end.replace("Z", "+00:00"))
        span_seconds = (dt_end - dt_start).total_seconds()
        assert span_seconds <= 600, f"Chat chunk {chk.chunk_id} exceeds 10 minutes span ({span_seconds}s)"
    print(f"[PASS] Check 5: All {len(chat_chunks)} chat chunks strictly respect limits (<=10 messages and <=10 minutes span).")

    # -------------------------------------------------------------
    # Check 6: Re-importing same file is caught by file_hash
    # -------------------------------------------------------------
    print("[RUNNING] Check 6: Testing duplicate file re-import rejection via file_hash...")
    deploy_path = data_dir / "deploy_log.txt"
    try:
        engine.ingest_file(deploy_path, incident_id, "deploy")
        assert False, "Engine failed to catch duplicate file import!"
    except ValueError as e:
        assert "Duplicate file import detected" in str(e)
    print("[PASS] Check 6: Re-importing deploy_log.txt was immediately caught and rejected by file_hash.")

    # -------------------------------------------------------------
    # Check 7: Fake token is redacted in stored text
    # -------------------------------------------------------------
    print("[RUNNING] Check 7: Verifying secret token redaction in stored text...")
    for ev in events:
        assert "xoxb-FAKE-0000-TEST" not in ev.text, f"Secret token leaked in event {ev.event_id}"
    for chk in chunks:
        assert "xoxb-FAKE-0000-TEST" not in chk.text, f"Secret token leaked in chunk {chk.chunk_id}"

    redacted_event = next(e for e in events if "[REDACTED_SECRET]" in e.text)
    assert redacted_event is not None
    print("[PASS] Check 7: Fake token 'xoxb-FAKE-0000-TEST' was safely masked as '[REDACTED_SECRET]'. Zero leaks in events or chunks.")

    # -------------------------------------------------------------
    # Check 8: All events in window & conflicting timestamps preserved
    # -------------------------------------------------------------
    print("[RUNNING] Check 8: Verifying incident window bounds and conflicting timestamp preservation...")
    window_start = datetime(2026, 10, 25, 13, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 10, 25, 15, 0, 0, tzinfo=timezone.utc)

    for ev in events:
        ev_dt = datetime.fromisoformat(ev.timestamp_utc.replace("Z", "+00:00"))
        assert window_start <= ev_dt <= window_end, f"Event {ev.event_id} ({ev.timestamp_utc}) outside incident window!"

    # Both conflicting timestamps are preserved:
    # 1. Chat claim: "it started at 14:02 UTC"
    chat_conflict_ev = next(e for e in events if "it started at 14:02 UTC" in e.text)
    assert chat_conflict_ev is not None

    # 2. Alert 4471 firing at 14:07:00Z
    alert_conflict_ev = next(e for e in events if e.event_id == "EVT-ALT-4471")
    assert alert_conflict_ev.timestamp_utc == "2026-10-25T14:07:00Z"

    print("[PASS] Check 8: All events fall inside 13:00-15:00 UTC window, and both conflicting timestamps (14:02 chat vs 14:07 alert) are intact.")

    print("\n=======================================================")
    print("  ALL 8 INGESTION VALIDATION CHECKS PASSED (100%)")
    print("=======================================================\n")


if __name__ == "__main__":
    run_ingestion_validation()
