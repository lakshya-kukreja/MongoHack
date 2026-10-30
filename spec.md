# Incident Timeline Investigator — System Specification

## 1. Project Overview & Objectives
**Incident Timeline Investigator** is a grounded Retrieval-Augmented Generation (RAG) and deterministic timeline analysis system designed for post-incident review and active incident triage. 

During an outage, engineering teams produce heterogeneous, fragmented data across:
1. **Chat Channels (e.g. Slack)**: Real-time observations, triage debates, command executions, and status updates.
2. **Monitoring & Alerting Systems (e.g. Datadog, PagerDuty, Prometheus)**: Latency spikes, error rate breaches, resource exhaustion.
3. **Deployment Logs & CI/CD Systems (e.g. GitHub Actions, ArgoCD, Kubernetes)**: Service releases, configuration rollouts, rollbacks.

### Core Problems Solved
- **Chronological Confusion**: LLMs alone frequently hallucinate event sequences, scramble timestamps, or infer cause-and-effect that violates physical chronology.
- **Hallucinated or Absent Citations**: Standard RAG pipelines frequently output plausible summaries without traceable links to the exact log entry or chat message.
- **Failure to Acknowledge Uncertainty**: Many AI systems assert conclusions even when data is contradictory, missing, or inconclusive.

### Design Philosophy
- **Deterministic Chronology First**: Timelines are sorted and filtered by verified ISO-8601 timestamps in code—never by the LLM.
- **Strict Grounding & Traceable Citations**: Every generated claim must cite exact event identifiers (`[SOURCE_ID]`).
- **Explicit Uncertainty**: The system strictly differentiates between proven facts, contradictory evidence, and unproven hypotheses.
- **Architectural Simplicity**: No opaque agent frameworks (no LangChain, no LangGraph). Transparent, modular Python backend with FastAPI and MongoDB Atlas Vector Search.

---

## 2. System Architecture

```
[Raw Event Records: JSON / JSONL]
  (Slack, Alerts, Deployments)
                 │
                 ▼
      ┌─────────────────────┐
      │  Ingestion Engine   │ ◄── Schema validation (Pydantic)
      └──────────┬──────────┘
                 │
                 ├── Generates Embeddings (Embedding Provider: text-embedding-3-small or Gemini)
                 │
                 ▼
      ┌──────────────────────────────────────────────────┐
      │            MongoDB Atlas Database                │
      │  Collection: `incident_events`                   │
      │  - Deterministic Metadata (timestamp, source_id) │
      │  - Raw Content & Normalized Payload              │
      │  - Vector Embeddings (`embedding` field)         │
      │  - Index: Atlas `$vectorSearch` Index            │
      └──────────────────┬───────────────────────────────┘
                         │
      ┌──────────────────┴───────────────────┐
      │                                      │
      ▼                                      ▼
┌───────────────────────────┐  ┌───────────────────────────────────┐
│   Deterministic Timeline  │  │   Vector Search & Filter Engine   │
│   Engine (Time range,     │  │   ($vectorSearch + Metadata       │
│   Incident ID, Actor/Type)│  │    pre-filters on Incident/Time)  │
└─────────────┬─────────────┘  └─────────────────┬─────────────────┘
              │                                  │
              │   ┌──────────────────────────────┘
              ▼   ▼
      ┌─────────────────────────────────────┐
      │ Grounded Context Assembly           │
      │ - Formatted Chronological Evidence  │
      │ - Source ID reference table         │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ LLM Generation Engine               │
      │ - Strict Grounding Prompt           │
      │ - Mandatory [SOURCE_ID] Citations   │
      │ - Missing/Contradictory checks      │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ Citation Validator & Post-Processor │
      │ - Verifies citations exist in ctx   │
      │ - Links IDs to full event metadata  │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ FastAPI REST API                    │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ React + TypeScript + Vite Frontend  │
      │ - Interactive Timeline View         │
      │ - Investigation Chat with Citations │
      │ - Deep-dive Event Inspector Drawer  │
      └─────────────────────────────────────┘
```

---

## 3. Incident Event Schema & Citation Contract

### 3.1 MongoDB Document & Pydantic Schema

Every event across Slack, monitoring, and deployments is normalized into a unified schema:

```json
{
  "_id": "ObjectId('...')",
  "source_id": "ALERT-201",
  "incident_id": "INC-2026-042",
  "timestamp": "2026-10-30T14:05:00Z",
  "source_type": "monitoring_alert",
  "author_or_actor": "datadog-monitor",
  "channel_or_service": "checkout-service",
  "summary": "P99 latency breach on /checkout > 2000ms",
  "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod.",
  "structured_payload": {
    "metric_name": "http_req_duration_p99",
    "threshold": 2000,
    "value": 2840,
    "severity": "CRITICAL",
    "environment": "production"
  },
  "embedding_text": "[ALERT] [2026-10-30T14:05:00Z] checkout-service (datadog-monitor): CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod.",
  "embedding": [0.0124, -0.0451, "...", 0.0892],
  "tags": ["latency", "checkout", "alert", "sev1"],
  "created_at": "2026-10-30T18:00:00Z"
}
```

#### Field Specifications:
- `source_id` (string, required, unique within incident): Human-readable stable reference code (e.g. `SLACK-301`, `ALERT-201`, `DEPLOY-101`).
- `incident_id` (string, required, indexed): Incident grouping key (e.g. `INC-2026-042`).
- `timestamp` (string / datetime, required, indexed): Canonical UTC timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`).
- `source_type` (string, required): One of `"slack"`, `"monitoring_alert"`, `"deployment_log"`.
- `author_or_actor` (string, required): Username, bot name, or deploying engineer/system.
- `channel_or_service` (string, required): Slack channel (e.g. `#incidents-prod`) or affected microservice/repo (e.g. `auth-service`, `payment-v2`).
- `summary` (string, required): Short one-line synopsis used for quick timeline rendering.
- `raw_content` (string, required): Full unaltered text of the message, alert payload, or deployment description.
- `structured_payload` (dict, optional): Strongly-typed attributes (error codes, commit hashes, latency numbers, cluster names).
- `embedding_text` (string, required): Canonical formatted representation used to compute vector embeddings.
- `embedding` (list[float], required): Vector embedding representation (1536 dims for OpenAI `text-embedding-3-small`, or 768 dims for Gemini).
- `tags` (list[string], optional): Categorical tags for hybrid/faceted search.

---

### 3.2 Citation Contract

To prevent hallucinated citations, the system enforces a strict citation lifecycle:

1. **Context Formulation**:
   Each retrieved event passed to the LLM prompt is labeled with an explicit delimiter:
   ```
   [EVIDENCE RECORD ALERT-201]
   Source ID: ALERT-201
   Timestamp: 2026-10-30T14:05:00Z
   Type: monitoring_alert | Service: checkout-service | Actor: datadog-monitor
   Content: CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms).
   ```

2. **LLM Generation Rule**:
   - The LLM must append citation markers like `[ALERT-201]` directly after claims derived from that event.
   - If a claim draws from multiple records, cite all relevant IDs: `[ALERT-201] [SLACK-301]`.
   - Never cite a source ID that is not listed in the retrieved context.
   - If no retrieved evidence answers the query, state: `"Based on the retrieved incident records, there is insufficient evidence to answer this question."` and cite nothing.

3. **Backend Citation Validation**:
   The response undergoes programmatic validation:
   - Regex extraction of all `\\[([A-Z]+-\\d+)\\]` tags in the generated answer.
   - Cross-check against the set of `source_id`s in the retrieved context documents.
   - If an unverified source ID is found, it is stripped or flagged with a warning.
   - Return structured citation objects alongside the text:
     ```json
     {
       "answer": "The initial alert triggered at 14:05:00Z when checkout latency spiked to 2840ms [ALERT-201]. Alice first acknowledged this in Slack four minutes later [SLACK-301].",
       "citations": [
         {
           "source_id": "ALERT-201",
           "source_type": "monitoring_alert",
           "timestamp": "2026-10-30T14:05:00Z",
           "author_or_actor": "datadog-monitor",
           "channel_or_service": "checkout-service",
           "summary": "P99 latency breach on /checkout > 2000ms"
         },
         {
           "source_id": "SLACK-301",
           "source_type": "slack",
           "timestamp": "2026-10-30T14:09:12Z",
           "author_or_actor": "alice.dev",
           "channel_or_service": "#incidents-prod",
           "summary": "Alice acknowledges checkout errors"
         }
       ],
       "unverified_citations": []
     }
     ```

4. **Frontend Interaction**:
   - The UI replaces `[ALERT-201]` with an interactive clickable badge `<CitationChip id="ALERT-201" />`.
   - Clicking the badge scrolls to and highlights that record on the timeline or opens the Event Inspector Drawer.

---

## 4. MongoDB Atlas Vector Search Specification

### 4.1 Vector Index Definition
The collection `incident_events` requires an Atlas Vector Search index (e.g. named `vector_index`).

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "incident_id"
    },
    {
      "type": "filter",
      "path": "source_type"
    },
    {
      "type": "filter",
      "path": "timestamp"
    }
  ]
}
```

### 4.2 Retrieval Query Pattern
To guarantee semantic relevance while restricting to the target incident and timeframe:

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",
            "queryVector": query_embedding,
            "numCandidates": 50,
            "limit": 10,
            "filter": {
                "incident_id": {"$eq": incident_id}
            }
        }
    },
    {
        "$project": {
            "_id": 1,
            "source_id": 1,
            "incident_id": 1,
            "timestamp": 1,
            "source_type": 1,
            "author_or_actor": 1,
            "channel_or_service": 1,
            "summary": 1,
            "raw_content": 1,
            "structured_payload": 1,
            "score": {"$meta": "vectorSearchScore"}
        }
    }
]
```

### 4.3 Deterministic Timeline Query Pattern
When rendering the incident chronology, vector search is **not** used. Instead, standard indexed sorting guarantees chronological truth:

```python
cursor = db.incident_events.find(
    {
        "incident_id": incident_id,
        "timestamp": {"$gte": start_time, "$lte": end_time}
    }
).sort("timestamp", 1)  # 1 = Ascending chronological order
```

---

## 5. RAG Engine & Prompting Strategy

### 5.1 System Prompt
```text
You are an expert Incident Timeline Investigator. Your duty is to analyze software incident evidence with extreme rigor, fidelity, and precision.

RULES:
1. ONLY make claims directly substantiated by the provided EVIDENCE RECORDS.
2. For EVERY factual claim you make, immediately append the citation token: [SOURCE_ID].
3. If multiple records support a claim, cite each: [SOURCE_ID_1] [SOURCE_ID_2].
4. NEVER invent, infer, or hallucinate a source ID.
5. CHRONOLOGY: Respect the timestamps provided in the evidence records. Do not alter or assume the sequence of events.
6. ROOT CAUSE & UNPROVEN HYPOTHESES:
   - Clearly distinguish proven facts (supported by metrics/logs/code changes) from human hypotheses or unverified conjectures in chat.
   - If an engineer speculated something was the root cause, but no metrics confirm it, explicitly label it as "Unverified Hypothesis by [Actor] ([SOURCE_ID])".
7. CONTRADICTIONS: If two pieces of evidence contradict each other, highlight the discrepancy explicitly.
8. INSUFFICIENT EVIDENCE: If the records do not contain enough evidence to answer a question, state: "Based on the retrieved records, there is insufficient evidence to determine [question]."
```

### 5.2 Retrieval Augmentation Flow
1. **User asks**: *"What was the first sign of trouble and who responded?"*
2. **Embedding**: Generate embedding for user question.
3. **Retrieval**: Query `$vectorSearch` with pre-filter `incident_id = "INC-2026-042"`.
4. **Context Construction**:
   - Format retrieved records in chronological order.
   - Append reference ID list.
5. **Generation**: LLM processes system prompt + context + user query.
6. **Validation**: Check returned text for citation conformity against retrieved `source_id`s.

---

## 6. REST API Endpoints Specification

| Method | Endpoint | Description | Request Body / Params | Response |
|---|---|---|---|---|
| `GET` | `/api/health` | Healthcheck & DB status | None | `{"status": "ok", "db": "connected"}` |
| `POST` | `/api/incidents/ingest` | Ingest raw JSON/JSONL records | Multipart file or JSON body | `{"incident_id": "...", "ingested_count": 15}` |
| `GET` | `/api/incidents` | List all available incidents | None | `[{"incident_id": "...", "event_count": 15, "start_time": "...", "end_time": "..."}]` |
| `GET` | `/api/incidents/{incident_id}/timeline` | Fetch deterministic chronological timeline | `start_time`, `end_time`, `source_type` | `{"incident_id": "...", "events": [...]}` |
| `POST` | `/api/incidents/{incident_id}/query` | Ask an investigation question (RAG) | `{"query": "...", "limit": 8}` | `{"answer": "...", "citations": [...], "retrieved_events": [...]}` |
| `GET` | `/api/incidents/{incident_id}/events/{source_id}` | Retrieve single event detail | None | `EventRecord` |

---

## 7. Security, Environment, and Configuration

- All secrets managed via `.env` (never committed to Git).
- Required variables:
  - `MONGODB_URI`: Connection string to MongoDB Atlas.
  - `MONGODB_DB_NAME`: Database name (e.g. `incident_investigator`).
  - `EMBEDDING_PROVIDER`: `"openai"` or `"gemini"`.
  - `EMBEDDING_API_KEY`: API key for embeddings.
  - `EMBEDDING_MODEL_NAME`: e.g. `text-embedding-3-small`.
  - `LLM_PROVIDER`: `"openai"` or `"gemini"`.
  - `LLM_API_KEY`: API key for LLM.
  - `LLM_MODEL_NAME`: e.g. `gpt-4o-mini` or `gemini-1.5-flash`.
  - `CORS_ORIGINS`: Allowed origins (e.g. `http://localhost:5173`).

