"""
Test Citation Accuracy:
1. Every cited event_id must exist in retrieved_ids.
2. Every timestamp quoted in the answer must match the actual stored event timestamp.
"""

import re
import pytest
from datetime import datetime, timezone


def test_cited_ids_exist_in_retrieved(eval_cases, adapter):
    """Verifies that no hallucinated citations exist (all cited IDs must be in retrieved_ids)."""
    for case in eval_cases:
        res = adapter(case["question"], window=case["window"])
        citations = res["citations"]
        retrieved_ids = set(res["retrieved_ids"])

        for cited_id in citations:
            assert cited_id in retrieved_ids, (
                f"Citation verification failed in {case['case_id']}: "
                f"Cited ID '{cited_id}' was not in retrieved candidates: {retrieved_ids}"
            )


def test_quoted_timestamps_match_stored_values(eval_cases, adapter, ground_truth):
    """
    Verifies that any quoted ISO or UTC timestamp in the generated answer text
    corresponds to a genuine event timestamp stored in ground truth.
    """
    valid_stored_timestamps = {
        ev["timestamp_utc"] for ev in ground_truth["expected_event_order_utc"]
    }
    # Valid UTC hours and minutes
    valid_hm = {ts[11:16] for ts in valid_stored_timestamps}

    # Allow valid known local server EDT and alert IST hours/minutes:
    # 09:40 EDT, 10:28 EDT, 10:35 EDT, 19:37 IST, 20:02 IST
    valid_local_hm = {"09:40", "10:28", "10:30", "10:32", "10:35", "19:37", "19:38", "19:40", "19:46", "20:02"}

    # ISO regex or HH:MM pattern
    iso_pattern = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b")
    hm_pattern = re.compile(r"\b(\d{2}:\d{2})(?::\d{2})?\s*(?:UTC|EDT|IST|\+05:30)?\b")

    for case in eval_cases:
        res = adapter(case["question"], window=case["window"])
        answer = res["answer_text"]

        # 1. Full ISO matches
        found_isos = iso_pattern.findall(answer)
        for iso_ts in found_isos:
            assert iso_ts in valid_stored_timestamps, f"Answer quoted fabricated ISO timestamp: {iso_ts}"

        # 2. HH:MM checks
        found_times = hm_pattern.findall(answer)
        for t in found_times:
            if ":" in t:
                assert (t in valid_hm or t in valid_local_hm), (
                    f"Answer quoted unrecognized time '{t}' in {case['case_id']}"
                )
