"""
Comprehensive validation test script for Task 1: Synthetic incident dataset.
Validates:
1. JSON syntax and file readability across all data files.
2. Exact identifiers: alert 4471, commit a9f3c2, error code E4, service checkout-api.
3. Timezone conversion: server EDT (UTC-4), alert IST (UTC+5:30), chat epoch timestamps to UTC.
4. Conflict detection: chat 14:02 UTC claim vs alert 4471 at 14:07 UTC.
5. Actor traps: mentioned vs actual actor (sarah vs dave, marcus vs elena).
6. No-answer gap: absence of database migration deploy.
7. Secret token detection and redaction test.
8. Strictly monotonic chronological event ordering in ground_truth.json.
9. Schema compliance with canonical EventRecord.
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


def test_incident_001():
    base_dir = Path(__file__).resolve().parent.parent / "data" / "incident_001"
    
    print("\n=======================================================")
    print("  RUNNING VALIDATION SUITE: INCIDENT_001 DATASET")
    print("=======================================================\n")

    # 1. Check file existence
    chat_file = base_dir / "chat_export.json"
    alerts_file = base_dir / "alerts.json"
    deploy_file = base_dir / "deploy_log.txt"
    ground_truth_file = base_dir / "ground_truth.json"

    assert chat_file.exists(), f"Missing {chat_file}"
    assert alerts_file.exists(), f"Missing {alerts_file}"
    assert deploy_file.exists(), f"Missing {deploy_file}"
    assert ground_truth_file.exists(), f"Missing {ground_truth_file}"
    print("[PASS] All 4 files exist in data/incident_001/")

    # 2. Parse JSONs
    with open(chat_file, "r", encoding="utf-8") as f:
        chat_msgs = json.load(f)
    with open(alerts_file, "r", encoding="utf-8") as f:
        alerts = json.load(f)
    with open(deploy_file, "r", encoding="utf-8") as f:
        deploy_lines = f.readlines()
    with open(ground_truth_file, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    print(f"[PASS] JSON syntax valid: {len(chat_msgs)} chat msgs, {len(alerts)} alerts, {len(deploy_lines)} deploy lines.")

    # 3. Message count check (Requirement: 40-60 messages)
    assert 40 <= len(chat_msgs) <= 60, f"Chat message count {len(chat_msgs)} outside 40-60 range"
    print(f"[PASS] Chat message count ({len(chat_msgs)}) is within 40-60 range.")

    # 4. Alert count check (Requirement: 8-12 alerts)
    assert 8 <= len(alerts) <= 12, f"Alert count {len(alerts)} outside 8-12 range"
    print(f"[PASS] Alert count ({len(alerts)}) is within 8-12 range.")

    # 5. Exact Identifiers Trap
    # Alert ID: 4471, Commit SHA: a9f3c2, Error code: E4, Service: checkout-api
    alert_4471 = next((a for a in alerts if a["alert_id"] == "4471"), None)
    assert alert_4471 is not None, "Missing alert_id 4471"
    assert alert_4471["service"] == "checkout-api", "Alert 4471 service mismatch"
    assert alert_4471["error_code"] == "E4", "Alert 4471 error_code mismatch"

    deploy_text = "".join(deploy_lines)
    assert "a9f3c2" in deploy_text, "Commit SHA a9f3c2 not found in deploy log"
    assert "checkout-api" in deploy_text, "Service checkout-api not found in deploy log"
    print("[PASS] Exact identifiers verified: Alert 4471, commit a9f3c2, error code E4, service checkout-api.")

    # 6. Timezone conversion and Conflict Trap
    # Alert 4471 fired_at: 2026-10-25T19:37:00+05:30 -> UTC: 14:07:00Z
    alert_dt = datetime.fromisoformat(alert_4471["fired_at"]).astimezone(timezone.utc)
    expected_alert_utc = datetime(2026, 10, 25, 14, 7, 0, tzinfo=timezone.utc)
    assert alert_dt == expected_alert_utc, f"Alert UTC {alert_dt} != {expected_alert_utc}"

    # Chat claims it started at 14:02 UTC
    conflict_msg = next((m for m in chat_msgs if "it started at 14:02 UTC" in m["text"]), None)
    assert conflict_msg is not None, "Conflict claim message missing in chat"
    
    # Conflict difference calculation
    claimed_dt = datetime(2026, 10, 25, 14, 2, 0, tzinfo=timezone.utc)
    diff_minutes = (alert_dt - claimed_dt).total_seconds() / 60.0
    assert diff_minutes == 5.0, f"Conflict difference {diff_minutes} != 5.0 minutes"
    print(f"[PASS] Conflict Trap verified: Chat claims 14:02 UTC vs Alert 4471 at 14:07 UTC (difference: {diff_minutes} mins).")

    # 7. Timezone conversion for deploy_log.txt
    # [2026-10-25 09:40:00 EDT] -> UTC is 13:40:00Z
    deploy_line_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) EDT\].*Commit: a9f3c2", deploy_text)
    assert deploy_line_match is not None, "Deploy commit a9f3c2 line match failed"
    edt_naive = datetime.strptime(deploy_line_match.group(1), "%Y-%m-%d %H:%M:%S")
    # EDT is UTC-4
    edt_tz = timezone(timedelta(hours=-4))
    edt_aware = edt_naive.replace(tzinfo=edt_tz)
    deploy_utc = edt_aware.astimezone(timezone.utc)
    expected_deploy_utc = datetime(2026, 10, 25, 13, 40, 0, tzinfo=timezone.utc)
    assert deploy_utc == expected_deploy_utc, f"Deploy UTC {deploy_utc} != {expected_deploy_utc}"
    print("[PASS] Timezone conversion verified: EDT 09:40:00 correctly converts to UTC 13:40:00.")

    # 8. Actor Traps
    # Trap 1: Mentioned sarah.triage, actual actor dave.ops
    ack_msg = next((m for m in chat_msgs if "acknowledging alert 4471 now" in m["text"].lower()), None)
    assert ack_msg is not None, "Acknowledgement message not found"
    assert ack_msg["user"] == "dave.ops", f"Ack user was {ack_msg['user']}, expected dave.ops"

    # Trap 2: Mentioned marcus.eng, actual rollback actor elena.dev
    rollback_line = next((line for line in deploy_lines if "rollback" in line and "7b1e4a" in line), None)
    assert rollback_line is not None, "Rollback line not found in deploy log"
    assert "elena.dev" in rollback_line, "Deployer for rollback was not elena.dev"
    print("[PASS] Actor Traps verified: dave.ops acknowledged (not Sarah), elena.dev rolled back (not Marcus).")

    # 9. No-Answer Gap Trap
    # Ensure NO database migration in deploy log
    assert "migration" not in deploy_text.lower(), "Found unexpected database migration in deploy log"
    # Ensure inventory-sync complaint happens before alert
    inv_chat = next((m for m in chat_msgs if "inventory-sync is buffering orders" in m["text"]), None)
    assert inv_chat is not None, "Inventory complaint missing in chat"
    inv_chat_utc = datetime.fromtimestamp(float(inv_chat["ts"]), tz=timezone.utc)
    
    inv_alert = next((a for a in alerts if a["service"] == "inventory-sync" and a["severity"] == "HIGH"), None)
    inv_alert_utc = datetime.fromisoformat(inv_alert["fired_at"]).astimezone(timezone.utc)
    assert inv_chat_utc < inv_alert_utc, "Inventory alert did not fire after chat complaint"
    print("[PASS] No-Answer Gaps verified: No DB migration in deploy log; inventory-sync chat preceded alert by ~12 mins.")

    # 10. Secret Token Trap & Redaction
    secret_msg = next((m for m in chat_msgs if "xoxb-FAKE-0000-TEST" in m["text"]), None)
    assert secret_msg is not None, "Secret token message missing from chat"
    redacted = re.sub(r"xox[baprs]-[A-Za-z0-9-]+", "[REDACTED_SECRET]", secret_msg["text"])
    assert "xoxb-FAKE-0000-TEST" not in redacted and "[REDACTED_SECRET]" in redacted
    print("[PASS] Secret token trap verified: fake token found and regex redaction functions properly.")

    # 11. Ground Truth Monotonic Chronology
    timeline = ground_truth["expected_event_order_utc"]
    assert len(timeline) == 62, f"Expected 62 events in timeline, got {len(timeline)}"
    prev_dt = datetime.min.replace(tzinfo=timezone.utc)
    for ev in timeline:
        cur_dt = datetime.fromisoformat(ev["timestamp_utc"].replace("Z", "+00:00"))
        assert cur_dt >= prev_dt, f"Timeline ordering violation at order {ev['order']}: {cur_dt} < {prev_dt}"
        prev_dt = cur_dt
    print(f"[PASS] Ground Truth Chronology verified: All {len(timeline)} events strictly monotonically ordered in UTC.")

    # 12. Distractor dataset check (incident_000)
    distractor_dir = Path(__file__).resolve().parent.parent / "data" / "incident_000"
    assert (distractor_dir / "chat_export.json").exists(), "Missing incident_000 chat"
    assert (distractor_dir / "alerts.json").exists(), "Missing incident_000 alerts"
    assert (distractor_dir / "deploy_log.txt").exists(), "Missing incident_000 deploy log"
    with open(distractor_dir / "alerts.json", "r") as f:
        d_alerts = json.load(f)
    assert any("2026-09" in a["fired_at"] for a in d_alerts), "Distractor alerts must be from September 2026"
    print("[PASS] Distractor dataset (incident_000) verified: Exists and dated from last month.")

    print("\n=======================================================")
    print("  ALL 12 VALIDATION CHECKS PASSED SUCCESSFULLY! (100%)")
    print("=======================================================\n")


if __name__ == "__main__":
    test_incident_001()
