# Incident Timeline Investigator — Live Demo Script

**Target Duration**: 6 to 7 minutes  
**Presenters**: Person 1 (Backend/Data) & Person 2 (Frontend/Demo Lead)  
**Incident**: `INC-2026-001` (checkout-api P99 latency surge after deployment)

---

## ⏱️ Timeline Overview

| Stage | Activity | Duration |
|---|---|---|
| **Step 1** | Import & UTC Normalization | 1:00 min |
| **Step 2** | Multi-Source Query & Timeline Reconstruction | 1:30 min |
| **Step 3** | Citation Deep-Dive (Raw Source Verification) | 1:00 min |
| **Step 4** | Faceted Filtering (Alerts Only & Service Isolation) | 1:00 min |
| **Step 5** | Unanswerable Query (Refusal & Evidence Gap) | 1:00 min |
| **Step 6** | Conflict Surfacing & Resolution | 1:00 min |

---

## 🎬 Step-by-Step Walkthrough

### Step 1: Ingestion & Normalization (1:00 min)

* **Action**:
  1. Navigate to the Ingestion panel on the left column.
  2. Select `data/incident_001/` folder (or drag in `chat_export.json`, `alerts.json`, and `deploy_log.txt`).
  3. Click **Import Evidence**.
* **What to Type**: None (click-based import).
* **Expected On-Screen Result**:
  * Status indicator turns green: `Sources imported: 3 files (SHA-256 verified)`.
  * Event counter increments: `62 events normalized to UTC (0 events lost)`.
  * Secret token `xoxb-FAKE-0000-TEST` is automatically masked as `[REDACTED_SECRET]`.
* **What to Say**:
  > *"During an outage, evidence is scattered across chat, alerts, and deploy logs in completely different timezones—Slack in epoch seconds, Datadog in IST (+05:30), and Kubernetes deploy logs in Server EDT (UTC-4). Our ingestion pipeline extracts all 62 raw records, computes SHA-256 file hashes to prevent duplicates, redacts sensitive secrets in-flight, and normalizes all events into canonical ISO-8601 UTC."*

---

### Step 2: Multi-Source Query (1:30 min)

* **Action**:
  1. In the investigation search box, type the core incident question.
  2. Press **Enter** or click **Investigate**.
* **What to Type**:
  ```text
  What was the first sign of trouble, and who acted on it?
  ```
* **Expected On-Screen Result**:
  * An evidence-backed answer is generated with citations:
    > *"The earliest sign of trouble was observed in chat by alice.dev at 14:02:10 UTC [SLACK-002], followed by Datadog Alert 4471 at 14:07:00 UTC [ALERT-4471]. Dave (dave.ops) acknowledged Alert 4471 at 14:09:45 UTC and assumed Incident Commander role [SLACK-006]."*
  * Interactive clickable badges appear: `[SLACK-002]`, `[ALERT-4471]`, `[SLACK-006]`.
  * The timeline displays the 3 events in strict chronological order.
* **What to Say**:
  > *"Notice how the RAG engine answers across three completely different systems. It identifies that Alice first saw the anomaly in Slack at 14:02, automated Alert 4471 fired at 14:07, and Dave acknowledged it. Crucially, notice our Actor Trap: Bob @mentioned Sarah in chat, but our system correctly identifies that Dave actually acknowledged the alert and became Incident Commander."*

---

### Step 3: Citation Deep-Dive & Audit Drawer (1:00 min)

* **Action**:
  1. Click the `[ALERT-4471]` citation badge.
  2. Click the `[SLACK-002]` citation badge.
* **What to Type**: None (click interaction).
* **Expected On-Screen Result**:
  * The slide-over **Event Inspector Drawer** opens on the right.
  * Clicking `[ALERT-4471]` displays the raw Datadog JSON payload:
    `severity: CRITICAL`, `error_code: E4`, `measured_p99_ms: 2840`.
  * Clicking `[SLACK-002]` displays the unaltered Slack message:
    `"Is anyone seeing latency creeping up on the checkout funnel? Grafana P99 curve looks steep."`
* **What to Say**:
  > *"Every single factual assertion links back to an immutable source record. When an incident commander or SRE clicks a citation chip, the Inspector Drawer pulls the exact raw JSON alert and the exact Slack message with its message timestamp. There is zero hallucination—if an ID is cited, it is guaranteed to exist in the database."*

---

### Step 4: Faceted Timeline Filtering (1:00 min)

* **Action**:
  1. Click the **Source Filter** toggle and select **Monitoring Alerts Only**.
  2. Next, toggle back and filter by Service: **`checkout-api`**.
* **What to Type**: None (dropdown/pill selection).
* **Expected On-Screen Result**:
  * Timeline instantly updates:
    * Under "Alerts Only", all chat and deployment rows vanish; only the 11 alert records appear sorted strictly by timestamp.
    * Under `checkout-api`, cross-service noise (cart rate-limits, notification worker) is excluded.
* **What to Say**:
  > *"Our timeline engine is 100% deterministic—we never ask an LLM to sort events. MongoDB indexes sort events chronologically in microseconds. An engineer can isolate alerts only, or zoom into checkout-api, seeing the exact degradation curve from Alert 4471 down to recovery Alert 4478."*

---

### Step 5: Unanswerable Query & Hallucination Refusal (1:00 min)

* **Action**:
  1. Ask an unanswerable question about an event that never occurred.
* **What to Type**:
  ```text
  Who deployed the database migration on postgres right before the incident?
  ```
* **Expected On-Screen Result**:
  * The system **refuses to invent** a timeline and displays a clear evidence gap notice:
    > *"REFUSAL: Based on the provided deployment audit logs and chat records, no database migration was deployed. Chat discussion in #incidents confirms that only service code updates were released, and no DDL or database migrations were executed."*
  * Citations list is empty (0 hallucinated citations).
* **What to Say**:
  > *"Standard RAG systems love to guess. If you ask who deployed a database migration, an LLM might guess Marcus or Bob. But our engine enforces strict evidence-only prompting: if the evidence does not contain the answer, the engine states what was searched and explicitly declines rather than inventing a hallucinated timeline."*

---

### Step 6: Conflict Surfacing (1:00 min)

* **Action**:
  1. Ask about the discrepancy between chat observations and automated monitoring.
* **What to Type**:
  ```text
  At what time did the checkout degradation start according to chat versus the monitoring alert?
  ```
* **Expected On-Screen Result**:
  * The response displays an amber **Conflict Card**:
    > *"CONFLICT IDENTIFIED: In chat, alice.dev asserts the degradation started at 14:02:00 UTC when latency began climbing [SLACK-003]. In contrast, automated Datadog Alert 4471 fired 5 minutes later at 14:07:00 UTC (19:37:00+05:30) [ALERT-4471]. Both timestamps are preserved."*
* **What to Say**:
  > *"In real incidents, humans and monitoring disagree. Here, Alice saw latency creeping up at 14:02, but the P99 threshold alert didn't fire until 14:07. Rather than silently picking one timestamp, our engine surfaces both timestamps with an explicit conflict note, allowing post-mortem reviewers to identify detection lag."*

---

## 🏁 Closing Summary (30 seconds)

> *"In summary, Incident Timeline Investigator provides:  
> 1. Deterministic chronological sorting directly in MongoDB.  
> 2. Zero hallucinated citations verified against retrieved evidence.  
> 3. Automatic secret redaction and conflict detection.  
> Thank you, and we welcome any questions!"*
