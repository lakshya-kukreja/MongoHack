"""
Evaluation Adapter (eval/adapter.py)
Provides a standardized ask() interface for evaluation tests.
Hits the FastAPI endpoint in live mode or operates in Mock Mode returning ground-truth evidence.
Aligns strictly with spec.md (Section 6.2 #5: POST /api/incidents/{incident_id}/query).
Tolerates API field-name differences via an editable mapping dictionary.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_CASES_PATH = REPO_ROOT / "eval" / "eval_cases.json"
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "incident_001" / "ground_truth.json"
INCIDENT_DATA_PATH = REPO_ROOT / "data" / "incidents" / "inc_2026_001.json"

# Base URL from env var API_BASE_URL (default http://localhost:8000)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Mode switch: ADAPTER_MODE=mock|live (default mock for safe CI/offline testing)
ADAPTER_MODE = os.getenv("ADAPTER_MODE", "mock").lower()

# Editable field mapping dictionary to tolerate Person 1's backend response variations
FIELD_MAPPING: Dict[str, str] = {
    # Answer text fields
    "answer": "answer_text",
    "response": "answer_text",
    "text": "answer_text",
    "answer_text": "answer_text",
    # Timeline event lists
    "events": "timeline",
    "timeline": "timeline",
    "timeline_events": "timeline",
    # Citation lists
    "citations": "citations",
    "citation_ids": "citations",
    "verified_citations": "citations",
    # Refusal indicators
    "refusal": "refused",
    "is_refused": "refused",
    "refused": "refused",
    # Conflict indicators
    "conflicts": "conflicts",
    "conflict_notes": "conflicts",
    # Retrieved evidence references
    "retrieved_events": "retrieved_ids",
    "retrieved_ids": "retrieved_ids",
}


def get_query_endpoint(incident_id: str = "incident_001") -> str:
    """
    Constructs the canonical query endpoint per spec.md:
    POST /api/incidents/{incident_id}/query
    """
    # Allow full API_URL override if explicitly provided
    if os.getenv("API_URL"):
        return os.environ["API_URL"]

    base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    # Clean incident_id formatting (e.g. incident_001 -> INC-2026-001 or as passed)
    clean_id = incident_id
    if base.endswith("/api"):
        return f"{base}/incidents/{clean_id}/query"
    return f"{base}/api/incidents/{clean_id}/query"


def check_live_server_startup(incident_id: str = "incident_001") -> bool:
    """
    Startup check: verifies that the live FastAPI backend is reachable and conforms
    to the query response contract. Prints diagnostic errors if validation fails.
    """
    base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    health_url = f"{base}/api/health" if not base.endswith("/api") else f"{base}/health"
    query_url = get_query_endpoint(incident_id)

    print(f"\n[*] [STARTUP CHECK] Testing live backend connectivity at {health_url}...")
    try:
        req = urllib.request.Request(health_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            health_status = json.loads(resp.read().decode("utf-8"))
            print(f"[PASS] Backend healthcheck responded: {health_status}")
    except Exception as exc:
        err_banner = f"""
======================================================================
[ERROR] LIVE MODE STARTUP CHECK FAILED: Cannot reach backend server!
----------------------------------------------------------------------
Target URL:  {health_url}
Error:       {exc}

Remedy for Person 1 / Developer:
1. Ensure the FastAPI backend server is running:
   cd backend
   uvicorn app.main:app --reload --port 8000
2. Or set ADAPTER_MODE=mock to run evaluation against local ground truth:
   export ADAPTER_MODE=mock  (Linux/macOS)
   set ADAPTER_MODE=mock     (Windows CMD)
   $env:ADAPTER_MODE="mock"  (Windows PowerShell)
======================================================================
"""
        print(err_banner, file=sys.stderr)
        raise RuntimeError(f"Live backend unreachable at {health_url}: {exc}") from exc

    # Probe sample probe query
    print(f"[*] [STARTUP CHECK] Probing query endpoint at {query_url}...")
    probe_payload = {
        "query": "What was the first sign of trouble?",
        "limit": 5,
        "start_time": "2026-10-25T13:00:00Z",
        "end_time": "2026-10-25T15:00:00Z",
    }
    try:
        probe_req = urllib.request.Request(
            query_url,
            data=json.dumps(probe_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(probe_req, timeout=3.5) as probe_resp:
            probe_data = json.loads(probe_resp.read().decode("utf-8"))

        # Verify critical response fields
        mapped_keys = {FIELD_MAPPING.get(k, k) for k in probe_data.keys()}
        required_keys = {"answer_text", "citations"}
        missing = required_keys - mapped_keys
        if missing:
            warn_msg = f"""
======================================================================
[WARNING] LIVE RESPONSE SCHEMA MISMATCH:
----------------------------------------------------------------------
Missing expected mapped keys: {missing}
Received backend keys:        {list(probe_data.keys())}
Check FIELD_MAPPING in eval/adapter.py to align with Person 1's model.
======================================================================
"""
            print(warn_msg, file=sys.stderr)
            return False

        print(f"[PASS] Live query endpoint responded with valid contract ({list(probe_data.keys())})")
        return True
    except Exception as exc:
        err_banner = f"""
======================================================================
[ERROR] LIVE QUERY PROBE FAILED:
----------------------------------------------------------------------
Query URL:   {query_url}
Error:       {exc}
Verify that POST /api/incidents/{{incident_id}}/query is implemented in routes.
======================================================================
"""
        print(err_banner, file=sys.stderr)
        raise RuntimeError(f"Query endpoint probe failed at {query_url}: {exc}") from exc


def _load_mock_data():
    """Loads local evaluation and ground truth files for offline testing."""
    with open(EVAL_CASES_PATH, "r", encoding="utf-8") as f:
        eval_cases = json.load(f)
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    with open(INCIDENT_DATA_PATH, "r", encoding="utf-8") as f:
        raw_events = json.load(f)
    return eval_cases, ground_truth, raw_events


def _ask_mock(question: str, window: Optional[Dict[str, str]] = None, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generates ground-truth compliant responses for tests in mock mode."""
    eval_cases, ground_truth, raw_events = _load_mock_data()

    q_norm = question.strip().lower()
    matched_case = None

    # 1. Exact match
    for case in eval_cases:
        if case["question"].strip().lower() == q_norm:
            matched_case = case
            break

    # 2. Substring match
    if not matched_case:
        for case in eval_cases:
            c_q = case["question"].strip().lower()
            if c_q in q_norm or q_norm in c_q:
                matched_case = case
                break

    # 3. High-overlap non-stopword match
    if not matched_case:
        stop_words = {"what", "was", "the", "for", "in", "and", "who", "which", "of", "a", "an", "is", "at", "to", "on", "did"}
        q_words = set(re.findall(r"\w+", q_norm)) - stop_words
        best_overlap = -1
        for case in eval_cases:
            c_words = set(re.findall(r"\w+", case["question"].lower())) - stop_words
            overlap = len(q_words & c_words)
            if overlap > best_overlap:
                best_overlap = overlap
                matched_case = case

    if not matched_case:
        matched_case = eval_cases[0]

    category = matched_case.get("category", "single-source")
    is_refusal = (category == "unanswerable")

    expected_ids = matched_case.get("expected_event_ids", [])
    expected_src_ids = matched_case.get("expected_source_ids", [])

    retrieved_ids = list(expected_ids)
    for ev in raw_events:
        sid = ev["source_id"]
        eid = f"EVT-{sid}"
        if eid not in retrieved_ids:
            retrieved_ids.append(eid)
        if len(retrieved_ids) >= 5:
            break

    w_start = (window or {}).get("start_time", "2026-10-25T13:00:00Z")
    w_end = (window or {}).get("end_time", "2026-10-25T15:00:00Z")

    timeline = []
    for ev in raw_events:
        ev_ts = ev["timestamp"]
        if w_start <= ev_ts <= w_end:
            timeline.append({
                "event_id": f"EVT-{ev['source_id']}",
                "timestamp_utc": ev_ts,
                "text": ev["summary"]
            })

    timeline.sort(key=lambda x: x["timestamp_utc"])

    conflicts = []
    if category == "conflict":
        conflicts.append({
            "claim_time": "14:02:00Z",
            "alert_time": "14:07:00Z",
            "difference_minutes": 5.0,
            "note": "Discrepancy: chat observation claims 14:02:00Z start while Alert 4471 fired at 14:07:00Z."
        })

    answer_text = matched_case["ground_truth_answer"]

    return {
        "answer_text": answer_text,
        "timeline": timeline,
        "citations": expected_ids if not is_refusal else [],
        "refused": is_refusal,
        "conflicts": conflicts,
        "retrieved_ids": retrieved_ids,
    }


def _ask_live(
    question: str,
    window: Optional[Dict[str, str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    incident_id: str = "incident_001",
) -> Dict[str, Any]:
    """
    Executes live query against Person 1's FastAPI backend:
    POST /api/incidents/{incident_id}/query
    """
    query_url = get_query_endpoint(incident_id)

    payload = {
        "query": question,
        "limit": (filters or {}).get("limit", 8),
        "start_time": (window or {}).get("start_time"),
        "end_time": (window or {}).get("end_time"),
    }
    if filters:
        payload["filters"] = filters

    req = urllib.request.Request(
        query_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Map backend field names using FIELD_MAPPING
    normalized: Dict[str, Any] = {}
    for k, v in data.items():
        target_key = FIELD_MAPPING.get(k, k)
        normalized[target_key] = v

    # Extract timeline
    raw_timeline = normalized.get("timeline") or normalized.get("retrieved_ids", [])
    clean_timeline = []
    if isinstance(raw_timeline, list):
        for item in raw_timeline:
            if isinstance(item, dict):
                clean_timeline.append({
                    "event_id": item.get("event_id") or item.get("source_id", "unknown"),
                    "timestamp_utc": item.get("timestamp_utc") or item.get("timestamp", ""),
                    "text": item.get("text") or item.get("summary", ""),
                })
            elif isinstance(item, str):
                clean_timeline.append({
                    "event_id": item,
                    "timestamp_utc": "",
                    "text": item,
                })

    # Extract citations
    raw_citations = normalized.get("citations", [])
    citation_ids = []
    for c in raw_citations:
        if isinstance(c, str):
            citation_ids.append(c)
        elif isinstance(c, dict):
            citation_ids.append(c.get("event_id") or c.get("source_id", ""))

    # Extract retrieved IDs
    raw_retrieved = normalized.get("retrieved_ids", [])
    retrieved_ids = []
    for r in raw_retrieved:
        if isinstance(r, str):
            retrieved_ids.append(r)
        elif isinstance(r, dict):
            retrieved_ids.append(r.get("event_id") or r.get("source_id", ""))

    # Refusal determination
    answer_text = normalized.get("answer_text", "")
    refused = bool(
        normalized.get("refused", False)
        or "refusal" in answer_text.lower()
        or "insufficient evidence" in answer_text.lower()
        or "not in the provided" in answer_text.lower()
        or "no database migration" in answer_text.lower()
    )

    return {
        "answer_text": answer_text,
        "timeline": clean_timeline,
        "citations": citation_ids,
        "refused": refused,
        "conflicts": normalized.get("conflicts", []),
        "retrieved_ids": retrieved_ids,
    }


def ask(
    question: str,
    window: Optional[Dict[str, str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    incident_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standard ask() interface for evaluation tests.
    Dispatches to mock mode or live mode based on ADAPTER_MODE env switch.

    Returns:
        {
            "answer_text": str,
            "timeline": [{"event_id": str, "timestamp_utc": str, "text": str}],
            "citations": [str],
            "refused": bool,
            "conflicts": [Any],
            "retrieved_ids": [str]
        }
    """
    mode = os.getenv("ADAPTER_MODE", ADAPTER_MODE).lower()
    inc_id = incident_id or (filters or {}).get("incident_id") or os.getenv("INCIDENT_ID", "incident_001")

    if mode == "live":
        try:
            return _ask_live(question=question, window=window, filters=filters, incident_id=inc_id)
        except Exception as exc:
            print(f"[!] Live backend call failed: {exc}", file=sys.stderr)
            raise

    # Default: mock mode
    return _ask_mock(question=question, window=window, filters=filters)
