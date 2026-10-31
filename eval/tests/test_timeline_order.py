"""
Test Timeline Ordering:
Verifies that timeline events are deterministically sorted strictly ascending by UTC timestamp.
"""

from datetime import datetime, timezone
import pytest


def test_timeline_strictly_sorted_by_utc(eval_cases, adapter):
    """
    Asserts that the timeline returned by the adapter is 100% monotonically
    ordered by ISO-8601 UTC timestamp (t_i <= t_{i+1}) with zero chronological violations.
    """
    for case in eval_cases:
        res = adapter(case["question"], window=case["window"])
        timeline = res["timeline"]
        if len(timeline) < 2:
            continue

        prev_dt = datetime.min.replace(tzinfo=timezone.utc)
        for idx, ev in enumerate(timeline):
            cur_dt = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
            assert cur_dt >= prev_dt, (
                f"Chronological ordering violation in case {case['case_id']} at index {idx}: "
                f"Event {ev.get('event_id')} ({cur_dt}) placed after {prev_dt}"
            )
            prev_dt = cur_dt
