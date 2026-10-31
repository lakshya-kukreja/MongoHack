"""
Test Refusal Correctness:
1. System correctly refuses on unanswerable queries (EVAL-009, EVAL-010).
2. NO false refusals on valid, answerable queries.
"""

import pytest


def test_refusal_on_unanswerable_cases(eval_cases, adapter):
    """Verifies that unanswerable queries return refused=True and explain the gap."""
    unanswerable_cases = [c for c in eval_cases if c["category"] == "unanswerable"]
    assert len(unanswerable_cases) == 2, "Expected exactly 2 unanswerable benchmark cases"

    for case in unanswerable_cases:
        res = adapter(case["question"], window=case["window"])
        assert res["refused"] is True, f"Failed refusal on unanswerable case: {case['case_id']}"

        # Ensure answer text explains that evidence is missing or absent
        ans_lower = res["answer_text"].lower()
        has_refusal_reason = any(
            phrase in ans_lower
            for phrase in [
                "refusal",
                "no database migration",
                "no alert",
                "not in the provided",
                "insufficient evidence",
                "absent",
            ]
        )
        assert has_refusal_reason, (
            f"Case {case['case_id']} refused without explaining the specific evidence gap: {res['answer_text']}"
        )


def test_no_false_refusals_on_answerable_cases(eval_cases, adapter):
    """Verifies that answerable queries are never falsely refused."""
    answerable_cases = [c for c in eval_cases if c["category"] != "unanswerable"]

    for case in answerable_cases:
        res = adapter(case["question"], window=case["window"])
        assert res["refused"] is False, (
            f"False Refusal detected on valid question {case['case_id']}: '{case['question']}'"
        )
        assert len(res["answer_text"].strip()) > 20, f"Empty answer on answerable case: {case['case_id']}"
