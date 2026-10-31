"""
Validation test for eval/eval_cases.json (exactly 10 benchmark cases).
"""

import json
from pathlib import Path


def test_eval_cases_integrity():
    eval_file = Path(__file__).resolve().parent.parent / "eval" / "eval_cases.json"
    assert eval_file.exists(), f"Missing {eval_file}"

    with open(eval_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Exactly 10 cases
    assert len(cases) == 10, f"Expected exactly 10 eval cases, got {len(cases)}"

    # Check categories distribution
    categories = [c["category"] for c in cases]
    single_source = [c for c in cases if c["category"] == "single-source"]
    multi_source = [c for c in cases if c["category"] == "multi-source"]
    exact_id = [c for c in cases if c["category"] == "exact-identifier"]
    conflict = [c for c in cases if c["category"] == "conflict"]
    unanswerable = [c for c in cases if c["category"] == "unanswerable"]

    assert len(single_source) == 3, f"Expected 3 single-source cases, got {len(single_source)}"
    assert len(multi_source) == 3, f"Expected 3 multi-source cases, got {len(multi_source)}"
    assert len(exact_id) == 1, f"Expected 1 exact-identifier case, got {len(exact_id)}"
    assert len(conflict) == 1, f"Expected 1 conflict case, got {len(conflict)}"
    assert len(unanswerable) == 2, f"Expected 2 unanswerable cases, got {len(unanswerable)}"

    # Required fields on each case
    req_fields = ["case_id", "category", "question", "window", "expected_event_ids", "ground_truth_answer"]
    for c in cases:
        for f in req_fields:
            assert f in c, f"Case {c.get('case_id')} missing field {f}"
        assert c["case_id"].startswith("EVAL-")
        assert len(c["question"]) > 10
        assert len(c["ground_truth_answer"]) > 20

    print(f"\n[PASS] eval/eval_cases.json verified: exactly 10 cases with proper category distributions and schemas.")


if __name__ == "__main__":
    test_eval_cases_integrity()
