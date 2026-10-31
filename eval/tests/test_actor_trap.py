"""
Test Actor Traps:
Distinguishes between a person who was @mentioned in a chat message
versus the actor who actually performed the operational action.
"""

import pytest


def test_triage_actor_distinction(eval_cases, adapter):
    """
    On EVAL-004 ("first sign + who acknowledged"):
    bob.lead @mentioned sarah.triage, but dave.ops actually acknowledged Alert 4471 and took IC.
    System must credit dave.ops as the responder, not Sarah.
    """
    case_004 = next(c for c in eval_cases if c["case_id"] == "EVAL-004")
    res = adapter(case_004["question"], window=case_004["window"])
    answer = res["answer_text"].lower()

    assert "dave" in answer, "Failed to identify dave.ops as the responder who acknowledged the alert"
    # Ensure Sarah is not falsely credited as having acknowledged
    assert "sarah acknowledged" not in answer, "Falsely credited mentioned user Sarah with acknowledging"


def test_rollback_actor_distinction(eval_cases, adapter):
    """
    On EVAL-005 ("who executed rollback"):
    dave.ops instructed marcus.eng to rollback, but elena.dev actually triggered rollback commit 7b1e4a.
    System must credit elena.dev as the deployer who executed rollback.
    """
    case_005 = next(c for c in eval_cases if c["case_id"] == "EVAL-005")
    res = adapter(case_005["question"], window=case_005["window"])
    answer = res["answer_text"].lower()

    assert "elena" in answer, "Failed to identify elena.dev as the engineer who executed the rollback"
    assert "marcus executed the rollback" not in answer, "Falsely credited Marcus with executing the rollback"
