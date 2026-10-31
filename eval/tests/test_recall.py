"""
Test Recall@K and Mean Recall across answerable benchmark cases.
"""

import pytest


def test_recall_at_k_per_case(eval_cases, adapter, default_k):
    """
    Computes recall@k for each answerable case:
    recall = |expected_ids ∩ retrieved_ids[:k]| / |expected_ids|
    """
    answerable_cases = [c for c in eval_cases if c["category"] != "unanswerable"]

    for case in answerable_cases:
        res = adapter(case["question"], window=case["window"])
        retrieved_k = res["retrieved_ids"][:default_k]

        expected_targets = case.get("expected_event_ids", [])
        if not expected_targets:
            continue

        # Check hits
        hits = set(expected_targets) & set(retrieved_k)
        recall = len(hits) / len(expected_targets)

        assert recall >= 0.5, (
            f"Case {case['case_id']} failed recall@{default_k}: "
            f"Expected {expected_targets}, got top-{default_k}: {retrieved_k}"
        )


def test_mean_recall_across_benchmark(eval_cases, adapter, default_k):
    """
    Calculates the Mean Recall@K across all answerable benchmark cases.
    Asserts overall retrieval performance meets or exceeds 0.8 (80%).
    """
    answerable_cases = [c for c in eval_cases if c["category"] != "unanswerable"]
    recalls = []

    for case in answerable_cases:
        res = adapter(case["question"], window=case["window"])
        retrieved_k = res["retrieved_ids"][:default_k]
        expected_targets = case.get("expected_event_ids", [])

        if not expected_targets:
            continue

        hits = set(expected_targets) & set(retrieved_k)
        recalls.append(len(hits) / len(expected_targets))

    mean_recall = sum(recalls) / len(recalls) if recalls else 0.0
    print(f"\n[BENCHMARK] Mean Recall@{default_k}: {mean_recall * 100:.1f}%")
    assert mean_recall >= 0.8, f"Mean Recall@{default_k} ({mean_recall:.2f}) fell below 0.80 target threshold"
