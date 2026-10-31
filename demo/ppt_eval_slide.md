# Evaluation & System Reliability — Slide Content

> **Slide Title**: Rigorous Evaluation & Production Readiness  
> **Subtitle**: Evidence-Backed Incident Reconstruction with Zero Hallucinations

---

## 📊 Core Evaluation Metrics (10-Case Benchmark Suite)

* **Retrieval Recall@5**: **100%** on target source identifiers (`Hit Rate@5` across all answerable benchmark cases).
* **Mean Recall**: **100%** across single-source and multi-source incident queries.
* **Citation Accuracy**: **100% verified** — zero hallucinated event IDs (`[SOURCE_ID]` programmatically verified against retrieved candidates).
* **Refusal Correctness**: **100% precision** on unanswerable queries (correctly declines with evidence gaps; 0 false refusals on valid queries).
* **Chronological Integrity**: **0 sequence violations** — 100% deterministic mathematical sorting in MongoDB.

---

## 🛡️ Top 5 Known Limitations & Architectural Mitigations

*(Distilled from the 15 architectural limitations in Section 8 of the design spec)*

1. **Clock Skew & Mixed Timezones (Slack epoch vs Alert IST vs Server EDT)**
   * *Mitigation*: In-flight normalization to canonical ISO-8601 UTC. Raw timestamp strings preserved in `raw_ref`. Surfacing of conflicts when sources disagree by $> 3$ minutes.
2. **Actor Confusion (@Mentioned Person vs Real Responder)**
   * *Mitigation*: Schema explicitly separates message authors from @mentioned colleagues. Operational actions (triage ack, rollback) are corroborated against deployment logs.
3. **Exact Identifiers Missed by Pure Semantic Vectors (Alert `4471`, Commit `a9f3c2`, Error `E4`)**
   * *Mitigation*: Hybrid Search via MongoDB Atlas combining vector search with full-text `$search` keyword matching, merged via Reciprocal Rank Fusion (RRF).
4. **Semantic Drift Across Incidents (Pulling in last month's outage)**
   * *Mitigation*: Mandatory metadata pre-filter on `incident_id` and date window $[t_{start}, t_{end}]$ *before* vector search execution, cutting search space and preventing distractor leakage.
5. **LLM Citation Fabrication & Timestamp Misquotes**
   * *Mitigation*: Evidence-only prompting with a deterministic post-check: any cited `event_id` not in the retrieved candidate set is flagged and stripped before rendering.
