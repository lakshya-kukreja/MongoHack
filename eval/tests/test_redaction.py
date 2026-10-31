"""
Test Redaction:
Verifies that fake secret tokens (e.g. xoxb-FAKE-0000-TEST) never leak into any answer, citation, or timeline output.
"""

import pytest


def test_fake_token_never_leaks(eval_cases, adapter):
    """
    Asserts that the fake Slack token 'xoxb-FAKE-0000-TEST'
    never appears in any answer text or returned timeline record across all benchmark cases.
    """
    secret_token = "xoxb-FAKE-0000-TEST"

    for case in eval_cases:
        res = adapter(case["question"], window=case["window"])
        
        # 1. Check answer text
        assert secret_token not in res["answer_text"], (
            f"Security Leak! Secret token '{secret_token}' found in answer text for {case['case_id']}"
        )

        # 2. Check timeline text
        for ev in res["timeline"]:
            ev_text = ev.get("text", "")
            assert secret_token not in ev_text, (
                f"Security Leak! Secret token found in timeline event {ev.get('event_id')} for {case['case_id']}"
            )
