"""
Test Filter Leakage:
1. Zero events from the distractor dataset (incident_000, September 2026).
2. Zero events outside the requested incident time window.
"""

from datetime import datetime, timezone
import pytest


def test_zero_leakage_from_incident_000(eval_cases, adapter):
    """
    Verifies that semantically similar events from last month's incident (incident_000)
    are strictly filtered out by the mandatory incident_id pre-filter.
    """
    for case in eval_cases:
        res = adapter(case["question"], window=case["window"])
        timeline = res["timeline"]
        retrieved_ids = res["retrieved_ids"]

        # Ensure no event contains September dates (2026-09)
        for ev in timeline:
            ts = ev.get("timestamp_utc", "")
            assert not ts.startswith("2026-09"), f"Leaked incident_000 September event into timeline: {ev}"

        for r_id in retrieved_ids:
            assert "3102" not in r_id and "3105" not in r_id and "3110" not in r_id, (
                f"Leaked incident_000 alert candidate {r_id} into retrieval results"
            )


def test_zero_events_outside_requested_window(eval_cases, adapter):
    """
    Verifies that all returned timeline events strictly fall within
    the requested [start_time, end_time] window bounds.
    """
    for case in eval_cases:
        window = case.get("window", {})
        if not window.get("start_time") or not window.get("end_time"):
            continue

        w_start = datetime.fromisoformat(window["start_time"].replace("Z", "+00:00"))
        w_end = datetime.fromisoformat(window["end_time"].replace("Z", "+00:00"))

        res = adapter(case["question"], window=window)
        for ev in res["timeline"]:
            ev_ts = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
            assert w_start <= ev_ts <= w_end, (
                f"Timeline event {ev.get('event_id')} ({ev['timestamp_utc']}) outside requested window: [{w_start}, {w_end}]"
            )
