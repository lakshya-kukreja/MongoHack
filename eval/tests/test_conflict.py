"""
Test Conflict Surfacing:
Verifies that conflicting evidence (14:02 chat claim vs 14:07 alert timestamp)
is actively surfaced with both timestamps and an explanatory conflict note, rather than silently guessed.
"""

import pytest


def test_conflict_surfaced(eval_cases, adapter):
    """
    On conflict test cases (EVAL-008), confirms:
    1. Both timestamps (14:02 and 14:07) are present in the response or conflict structure.
    2. An explicit conflict or discrepancy note is reported.
    """
    conflict_cases = [c for c in eval_cases if c["category"] == "conflict"]
    assert len(conflict_cases) >= 1, "Expected at least 1 conflict test case"

    for case in conflict_cases:
        res = adapter(case["question"], window=case["window"])
        answer = res["answer_text"].lower()
        conflicts = res.get("conflicts", [])

        # Check for both timestamps in answer or structured conflict notes
        has_1402 = "14:02" in answer or any("14:02" in str(c) for c in conflicts)
        has_1407 = "14:07" in answer or any("14:07" in str(c) for c in conflicts)

        assert has_1402, "Chat claim timestamp 14:02 missing from conflict response"
        assert has_1407, "Alert timestamp 14:07 missing from conflict response"

        # Check for explicit conflict note or flag
        has_conflict_flag = (
            len(conflicts) > 0
            or "conflict" in answer
            or "discrepancy" in answer
            or "difference" in answer
        )
        assert has_conflict_flag, "System failed to explicitly surface the timestamp conflict"
