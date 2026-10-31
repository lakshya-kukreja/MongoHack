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

## 2. System Architecture & Implementation Status

```
[Raw Event Records: JSON / JSONL] ◄── [IMPLEMENTED: data/incidents/inc_2026_042.json (17 events)]
  (Slack, Alerts, Deployments)
                 │
                 ▼
      ┌─────────────────────┐
      │  Ingestion Engine   │ ◄── [IMPLEMENTED: backend/app/services/ingestion.py]
      └──────────┬──────────┘
                 │
                 ├── Generates Embeddings (Gemini default / OpenAI supported) ◄── [BE-106, BE-113: embeddings.py]
                 │
                 ▼
      ┌──────────────────────────────────────────────────┐
      │            MongoDB Atlas Database                │ ◄── [IMPLEMENTED: storage.py, atlas_vector_index.json]
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
│   Deterministic Timeline  │  │   Vector Search & Filter Engine   │ ◄── [PLANNED: BE-107: retrieval.py]
│   Engine (Time range,     │  │   ($vectorSearch + Metadata       │
│   Incident ID, Actor/Type)│  │    pre-filters on Incident/Time)  │
│   [IMPLEMENTED]           │  └─────────────────┬─────────────────┘
└─────────────┬─────────────┘                    │
              │                                  │
              │   ┌──────────────────────────────┘
              ▼   ▼
      ┌─────────────────────────────────────┐
      │ Grounded Context Assembly           │ ◄── [PLANNED: BE-108: generator.py]
      │ - Formatted Chronological Evidence  │
      │ - Source ID reference table         │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ LLM Generation Engine               │ ◄── [PLANNED: BE-108: generator.py]
      │ - Strict Grounding Prompt           │
      │ - Mandatory [SOURCE_ID] Citations   │
      │ - Missing/Contradictory checks      │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ Citation Validator & Post-Processor │ ◄── [PLANNED: BE-108: generator.py]
      │ - Verifies citations exist in ctx   │
      │ - Links IDs to full event metadata  │
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ FastAPI REST API                    │ ◄── [PARTIALLY IMPLEMENTED: backend/app/api/incidents.py]
      │ - Health, Ingest, Timeline, Events  │     (Query endpoint PLANNED in BE-109)
      └──────────────────┬──────────────────┘
                         │
                         ▼
      ┌─────────────────────────────────────┐
      │ React + TypeScript + Vite Frontend  │ ◄── [IMPLEMENTED on frontend branch: Timeline, Chat, Drawer]
      │ - Interactive Timeline View         │
      │ - Investigation Chat with Citations │
      │ - Deep-dive Event Inspector Drawer  │
      └─────────────────────────────────────┘
```

### Component Status Matrix

| Component | Module / Path | Owner | Status | Details |
|---|---|---|---|---|
| **Pydantic Models** | `backend/app/models/event.py` | Person 1 | **IMPLEMENTED** | `EventRecord`, `TimelineResponse`, `IncidentSummary`, `IngestRequest`, `IngestResponse`, `HealthResponse`. |
| **Ingestion Engine** | `backend/app/services/ingestion.py` | Person 1 | **IMPLEMENTED** | Heterogeneous normalization for Slack, Alerts, and Deployments. Enforces unique `source_id` and UTC datetimes. |
| **Storage Service** | `backend/app/services/storage.py` | Person 1 | **IMPLEMENTED** | MongoDB Atlas CRUD, index creation, in-memory mock fallback, duplicate handling, incident listing aggregation. |
| **Timeline Engine** | `backend/app/services/timeline.py` | Person 1 | **IMPLEMENTED** | Pure deterministic sorting ascending by timestamp, inclusive time-windowing, and source-type filtering. |
| **REST API (Core)** | `backend/app/api/incidents.py` | Person 1 | **IMPLEMENTED** | `/api/health`, `/api/incidents/ingest`, `/api/incidents`, `/api/incidents/{id}/timeline`, `/api/incidents/{id}/events/{source_id}`. |
| **Vector Embeddings** | `backend/app/services/embeddings.py` | Person 1 | **DONE (BE-106, BE-113)** | Gemini `gemini-embedding-2` (1536 dims) by default; OpenAI `text-embedding-3-small` remains supported. Batching, dimension validation, and rate limiting included. |
| **Atlas Vector Search** | `backend/app/services/retrieval.py` | Person 1 | **PLANNED (BE-107)** | `$vectorSearch` pipeline execution with metadata pre-filtering by `incident_id`. |
| **RAG Generator** | `backend/app/services/generator.py` | Person 1 | **PLANNED (BE-108)** | Strict grounding prompt formulation, citation extraction, validation against retrieved IDs, uncertainty handling. |
| **Query Endpoint** | `POST /api/incidents/{id}/query` | Person 1 | **PLANNED (BE-109)** | Investigation question endpoint returning `QueryResponse` with structured citations. |
| **Frontend UI** | `frontend/src/` | Person 2 | **IMPLEMENTED (branch)** | TanStack Router, TimelineView, ChatInterface, CitationChip, EventDrawer, DashboardView, Import, mockApi. |
| **Frontend Test Suite** | `frontend/src/test/` | Person 2 | **IN PROGRESS (branch)** | Mock API and route matching unit tests. Full build and component test verification pending dependencies. |
| **Golden Incident Data** | `data/incidents/inc_2026_042.json` | Person 3 | **IMPLEMENTED** | 17 verified events covering incident lifecycle from deploy to recovery and unproven hypothesis. |
| **Benchmark Cases** | `data/eval_cases.json` | Person 3 | **IMPLEMENTED** | 6 golden evaluation cases with expected source IDs, acceptable supplementary IDs, and negative query. |
| **Evaluation Harness** | `tests/test_retrieval_eval.py` | Person 3 | **PLANNED (DATA-303)** | Automated benchmark runner computing Hit Rate@K, MRR, latency, and citation precision. |

---

## 3. Incident Event Schema & Citation Contract

### 3.1 MongoDB Document & Pydantic Schema `[IMPLEMENTED]`

Every event across Slack, monitoring, and deployments is normalized into a unified schema defined in `backend/app/models/event.py`:

```json
{
  "_id": "ObjectId('...')",
  "source_id": "ALERT-201",
  "incident_id": "INC-2026-042",
  "timestamp": "2026-10-30T14:02:00Z",
  "source_type": "monitoring_alert",
  "author_or_actor": "datadog-monitor",
  "channel_or_service": "checkout-service",
  "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
  "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod on endpoint /api/v1/checkout.",
  "structured_payload": {
    "metric": "p99_latency_ms",
    "threshold": 2000,
    "measured_value": 2840,
    "severity": "CRITICAL",
    "endpoint": "/api/v1/checkout"
  },
  "embedding_text": "[ALERT] [2026-10-30T14:02:00Z] checkout-service (datadog-monitor): CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod on endpoint /api/v1/checkout.",
  "embedding": [0.0124, -0.0451, "...", 0.0892],
  "tags": ["alert", "latency", "critical", "checkout"],
  "created_at": "2026-10-30T18:00:00Z"
}
```

#### Field Specifications:
- `source_id` (string, required, unique within incident): Human-readable stable reference code (e.g. `SLACK-301`, `ALERT-201`, `DEPLOY-101`).
- `incident_id` (string, required, indexed): Incident grouping key (e.g. `INC-2026-042`).
- `timestamp` (datetime, required, indexed): Canonical UTC timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`).
- `source_type` (string enum, required): One of `"slack"`, `"monitoring_alert"`, `"deployment_log"`.
- `author_or_actor` (string, required): Username, bot name, or deploying engineer/system.
- `channel_or_service` (string, required): Slack channel (e.g. `#incidents-prod`) or affected microservice/repo (e.g. `checkout-service`).
- `summary` (string, required): Short one-line synopsis used for quick timeline rendering.
- `raw_content` (string, required): Full unaltered text of the message, alert payload, or deployment description.
- `structured_payload` (dict, optional): Strongly-typed attributes (error codes, commit hashes, latency numbers, cluster names).
- `embedding_text` (string, required): Canonical formatted representation used to compute vector embeddings.
- `embedding` (list[float], optional/required for search): Vector embedding representation. Must match the Atlas vector index: 1536 dims. For `models.batchEmbedContents`, Gemini `gemini-embedding-2`/`gemini-embedding-001` are requested at 1536 dims via the per-request top-level `EmbedContentRequest.outputDimensionality` field; the nested `embedContentConfig` object is only honored by `models.embedContent` and is ignored by the batch endpoint. OpenAI `text-embedding-3-small` outputs 1536 dims natively. Raw Gemini vectors are validated at exactly 1536 dims before normalization, and `gemini-embedding-001` output below its native 3072 dims is L2-normalized by the client as required by the Gemini API guidance.
- `tags` (list[string], optional): Categorical tags for hybrid/faceted search.
- `created_at` (datetime, optional): Ingestion timestamp in UTC.

---

### 3.2 Citation Contract `[PLANNED in BE-108; SIMULATED in FE mockApi.ts]`

To prevent hallucinated citations, the system enforces a strict citation lifecycle:

1. **Context Formulation**:
   Each retrieved event passed to the LLM prompt is labeled with an explicit delimiter:
   ```text
   [EVIDENCE RECORD ALERT-201]
   Source ID: ALERT-201
   Timestamp: 2026-10-30T14:02:00Z
   Type: monitoring_alert | Service: checkout-service | Actor: datadog-monitor
   Summary: CRITICAL: P99 latency breach on /checkout > 2000ms
   Content: CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod on endpoint /api/v1/checkout.
   ```

2. **LLM Generation Rule**:
   - The LLM must append citation markers like `[ALERT-201]` directly after claims derived from that event.
   - If a claim draws from multiple records, cite all relevant IDs: `[ALERT-201] [SLACK-301]`.
   - NEVER cite a source ID that is not listed in the retrieved context.
   - If no retrieved evidence answers the query, state: `"Based on the retrieved incident records, there is insufficient evidence to answer this question."` and cite nothing.

3. **Backend Citation Validation & Structure**:
   The response undergoes programmatic validation:
   - Regex extraction of all `\\[([A-Z]+-\\d+)\\]` tags in the generated answer.
   - Cross-check against the set of `source_id`s in the retrieved context documents.
   - If an unverified source ID is found, it is stripped from citations and returned in `unverified_citations`.
   - Return structured citation objects alongside the text:
     ```json
     {
       "answer": "The initial alert triggered at 14:02:00Z when checkout latency spiked to 2840ms [ALERT-201]. Alice first acknowledged this in Slack two minutes later [SLACK-301].",
       "citations": [
         {
           "source_id": "ALERT-201",
           "source_type": "monitoring_alert",
           "timestamp": "2026-10-30T14:02:00Z",
           "author_or_actor": "datadog-monitor",
           "channel_or_service": "checkout-service",
           "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
           "snippet": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms)."
         },
         {
           "source_id": "SLACK-301",
           "source_type": "slack",
           "timestamp": "2026-10-30T14:04:10Z",
           "author_or_actor": "alice.dev",
           "channel_or_service": "#incidents-prod",
           "summary": "Alice notices checkout latency alert",
           "snippet": "Seeing an alert for checkout latency. Investigating error rates on Stripe webhooks."
         }
       ],
       "unverified_citations": []
     }
     ```

4. **Frontend Interaction**:
   - The UI replaces `[ALERT-201]` tokens with an interactive clickable badge `<CitationChip id="ALERT-201" />`.
   - Unverified citations are rendered with a warning badge and explanatory tooltip.
   - Clicking the badge scrolls to and highlights that record on the timeline and/or opens the Event Inspector Drawer with full raw details and payload metrics.

---

## 4. MongoDB Atlas Vector Search & Deterministic Timeline Specification

### 4.1 Vector Index Definition `[IMPLEMENTED: backend/atlas_vector_index.json]`
The collection `incident_events` requires an Atlas Vector Search index whose name matches `VECTOR_INDEX_NAME` (canonical default: `vector_index`). The deployed index name is chosen when the index is created and **must match exactly**: Atlas `$vectorSearch` silently returns zero documents for an unknown index name instead of raising, which would otherwise surface as a misleading insufficient-evidence answer. The name may be overridden via `VECTOR_INDEX_NAME` for deployments that used a different name.

```json
{
  "name": "vector_index",
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

### 4.2 Retrieval Query Pattern `[IMPLEMENTED: BE-107, BE-117]`
To guarantee semantic relevance while restricting to the target incident and timeframe:

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": settings.VECTOR_INDEX_NAME,
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
            "_id": 0,
            "source_id": 1,
            "incident_id": 1,
            "timestamp": 1,
            "source_type": 1,
            "author_or_actor": 1,
            "channel_or_service": 1,
            "summary": 1,
            "raw_content": 1,
            "structured_payload": 1,
            "tags": 1,
            "embedding_text": 1,
            "score": {"$meta": "vectorSearchScore"}
        }
    }
]
```

### 4.3 Deterministic Timeline Query Pattern & Date-Filtering Behavior `[IMPLEMENTED]`
When rendering the incident chronology, vector search is **never** used. Instead, standard indexed sorting guarantees chronological truth:

```python
cursor = db.incident_events.find(
    {
        "incident_id": incident_id,
        "timestamp": {"$gte": start_time, "$lte": end_time}
    }
).sort("timestamp", 1)  # 1 = Ascending chronological order (deterministic)
```

#### Date-Filtering Behavior Rules:
- **Format**: Timestamps must be valid ISO-8601 strings in UTC (e.g., `2026-10-30T14:00:00Z`).
- **Boundaries**: Both bounds are **inclusive** (`timestamp >= start_time` AND `timestamp <= end_time`).
- **Omission Defaults**:
  - If `start_time` is omitted: Query defaults to the earliest recorded event of the incident.
  - If `end_time` is omitted: Query defaults to the latest recorded event of the incident.
  - If both are omitted: Returns all events for the incident in ascending order.
- **Validation**: If a supplied timestamp fails ISO-8601 parsing, the API returns HTTP 422 with `{"detail": "Invalid ISO-8601 datetime format for start_time/end_time"}`.
- **Filtering by Source Type**: The optional `source_type` query param accepts comma-separated values (e.g., `?source_type=slack,monitoring_alert`) to narrow results to specific data streams without breaking chronological ordering.

---

## 5. RAG Engine & Prompting Strategy `[PLANNED in BE-108]`

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
8. INSUFFICIENT EVIDENCE: If the records do not contain enough evidence to answer a question, state: "Based on the retrieved incident records, there is insufficient evidence to answer this question."
```

### 5.2 Retrieval Augmentation Flow
1. **User asks**: *"What was the first sign of trouble and who responded?"*
2. **Embedding**: Generate embedding for user question via `embeddings.py`.
3. **Retrieval**: Query `$vectorSearch` with pre-filter `incident_id = "INC-2026-042"`.
4. **Context Construction**:
   - Format retrieved records in chronological order.
   - Append reference ID list.
5. **Generation**: LLM processes system prompt + context + user query.
6. **Validation**: Check returned text for citation conformity against retrieved `source_id`s, strip hallucinations, return structured citations.

### 5.3 Error Handling, Timeouts & Upstream Resilience `[IMPLEMENTED]`
- **Upstream Timeouts**: Direct API calls to OpenAI or Gemini configure explicit limits (10 seconds for embeddings, 30 seconds per LLM generation attempt). A request that exceeds the overall deadline raises `HTTPException(status_code=504, detail="LLM provider timed out")`.
- **Bounded Retries & Deadline (BE-123)**: Generation retries transient upstream failures — HTTP 429, 500, 502, 503, 504, plus connect/pool transport timeouts — using exponential backoff with jitter (base `0.5s`, cap `4.0s`, default 3 total attempts). Permanent client errors (400/401/403/404) and read/write timeouts are never retried. `LLM_REQUEST_DEADLINE_SECONDS` (default `30.0`) is a hard wall-clock budget shared by all attempts and backoff sleeps, so retries cannot silently extend the documented 30s contract; when it is spent, the last safe provider diagnostic is surfaced. Retry logs include provider, model, status/phase, attempt, and delay only — never prompts, payloads, or API keys.
- **Gemini Thinking Configuration (BE-123)**: `LLM_GEMINI_THINKING_LEVEL` (default `low`) is sent only to Gemini as `generationConfig.thinkingConfig.thinkingLevel` (canonical enum `MINIMAL`/`LOW`/`MEDIUM`/`HIGH`). An empty value or `none`/`off`/`default` omits `thinkingConfig` and accepts the provider default. OpenAI payloads are unchanged and never receive Gemini thinking fields.
- **Rate Limits (HTTP 429) & Provider Failures (HTTP 5xx)**: After the retry budget is exhausted, failures are caught gracefully and mapped to `HTTPException(status_code=503, detail="LLM provider unavailable or rate-limited")`. Raw stack traces or secret keys must never leak to the client.
- **Negative & Insufficient Evidence Guarantees**: When retrieved evidence cannot answer the question or query matches negative evaluation criteria (e.g. EVAL-006), the response is HTTP 200 with `answer = "Based on the retrieved incident records, there is insufficient evidence to answer this question."`, `citations = []`, and `unverified_citations = []`.
- **Deterministic Offline Testing**: All test suites in `tests/` operate with mock embedding vectors and mock LLM generation responses, enabling rapid, 100% offline CI verification without consuming API tokens or requiring network access.
- **Live Integration & Demo Modes**: An opt-in live test suite and demonstration script (`scripts/demo_rag.py`) conditionally run against real cloud credentials when `LLM_API_KEY`, `EMBEDDING_API_KEY`, and `MONGODB_URI` are supplied in `.env`. The application reads the provider-neutral `LLM_*` / `EMBEDDING_*` variables and does **not** read `OPENAI_API_KEY` or `GEMINI_API_KEY` directly.

---

## 6. REST API Endpoints Specification & Contracts

### 6.1 Endpoints Overview

| Method | Endpoint | Description | Status | Request | Response |
|---|---|---|---|---|---|
| `GET` | `/api/health` | Healthcheck & DB status | **IMPLEMENTED** | None | `HealthResponse` |
| `POST` | `/api/incidents/ingest` | Ingest JSON array of incident records | **IMPLEMENTED** | `IngestRequest` | `IngestResponse` |
| `GET` | `/api/incidents` | List all available incidents with summary | **IMPLEMENTED** | None | `list[IncidentSummary]` |
| `GET` | `/api/incidents/{incident_id}/timeline` | Fetch deterministic chronological timeline | **IMPLEMENTED** | Query params: `start_time`, `end_time`, `source_type` | `TimelineResponse` |
| `GET` | `/api/incidents/{incident_id}/events/{source_id}` | Retrieve single event detail | **IMPLEMENTED** | Path params | `EventRecord` |
| `POST` | `/api/incidents/{incident_id}/query` | Ask an investigation question (RAG) | **PLANNED (BE-109)** | `QueryRequest` | `QueryResponse` |
| `GET` | `/api/investigations` | List saved investigation sessions | **PLANNED EXTENSION** | None | `list[Investigation]` |
| `POST` | `/api/investigations` | Save an investigation session | **PLANNED EXTENSION** | `Investigation` | `Investigation` |

---

### 6.2 Detailed Request & Response Formats

#### 1. `GET /api/health` `[IMPLEMENTED]`
- **Response** (`200 OK`):
```json
{
  "status": "ok",
  "database": "connected",
  "version": "1.0.0"
}
```

#### 2. `POST /api/incidents/ingest` `[IMPLEMENTED]`
- **Request Body** (`application/json`):
```json
{
  "incident_id": "INC-2026-042",
  "events": [
    {
      "source_id": "ALERT-201",
      "timestamp": "2026-10-30T14:02:00Z",
      "source_type": "monitoring_alert",
      "author_or_actor": "datadog-monitor",
      "channel_or_service": "checkout-service",
      "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
      "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold...",
      "structured_payload": {"metric": "p99", "threshold": 2000, "measured_value": 2840},
      "tags": ["alert", "latency"]
    }
  ]
}
```
- **Response** (`201 Created`):
```json
{
  "incident_id": "INC-2026-042",
  "ingested_count": 17,
  "status": "success"
}
```

#### 3. `GET /api/incidents` `[IMPLEMENTED]`
- **Response** (`200 OK`):
```json
[
  {
    "incident_id": "INC-2026-042",
    "title": "Payment Gateway P99 Latency Spike & Cascading Connection Pool Exhaustion",
    "event_count": 17,
    "start_time": "2026-10-30T13:45:00Z",
    "end_time": "2026-10-30T14:45:00Z",
    "services_involved": ["checkout-service", "postgres-db-primary"]
  }
]
```

#### 4. `GET /api/incidents/{incident_id}/timeline` `[IMPLEMENTED]`
- **Query Parameters**:
  - `start_time` (string, optional): ISO-8601 string (e.g., `2026-10-30T14:00:00Z`).
  - `end_time` (string, optional): ISO-8601 string (e.g., `2026-10-30T14:30:00Z`).
  - `source_type` (string, optional): Comma-delimited list of source types (e.g., `slack,monitoring_alert`).
- **Response** (`200 OK`):
```json
{
  "incident_id": "INC-2026-042",
  "total_events": 17,
  "filtered_count": 17,
  "events": [
    {
      "source_id": "DEPLOY-101",
      "incident_id": "INC-2026-042",
      "timestamp": "2026-10-30T13:45:00Z",
      "source_type": "deployment_log",
      "author_or_actor": "devops-bot",
      "channel_or_service": "checkout-service",
      "summary": "Deployment of checkout-service v2.4.1 to production",
      "raw_content": "DEPLOYMENT SUCCESSFUL: checkout-service v2.4.1...",
      "structured_payload": {"version": "v2.4.1", "commit": "a1f9c8d"},
      "tags": ["deployment", "release"]
    }
  ]
}
```

#### 5. `GET /api/incidents/{incident_id}/events/{source_id}` `[IMPLEMENTED]`
- **Response** (`200 OK`):
```json
{
  "source_id": "ALERT-201",
  "incident_id": "INC-2026-042",
  "timestamp": "2026-10-30T14:02:00Z",
  "source_type": "monitoring_alert",
  "author_or_actor": "datadog-monitor",
  "channel_or_service": "checkout-service",
  "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
  "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms). Triggered by rule LatencyAlert-Prod on endpoint /api/v1/checkout.",
  "structured_payload": {
    "metric": "p99_latency_ms",
    "threshold": 2000,
    "measured_value": 2840,
    "severity": "CRITICAL",
    "endpoint": "/api/v1/checkout"
  },
  "tags": ["alert", "latency", "critical", "checkout"]
}
```

#### 6. `POST /api/incidents/{incident_id}/query` `[PLANNED: BE-109]`
- **Request Body** (`application/json`):
```json
{
  "query": "What was the first sign of trouble and who noticed it?",
  "limit": 8,
  "start_time": null,
  "end_time": null
}
```
- **Response** (`200 OK`):
```json
{
  "answer": "The first sign of trouble was at 14:02:00Z when Datadog issued a CRITICAL alert showing P99 latency exceeded 2000ms [ALERT-201]. Alice first noticed it in #incidents-prod at 14:04:10Z [SLACK-301].",
  "citations": [
    {
      "source_id": "ALERT-201",
      "source_type": "monitoring_alert",
      "timestamp": "2026-10-30T14:02:00Z",
      "author_or_actor": "datadog-monitor",
      "channel_or_service": "checkout-service",
      "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
      "snippet": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms)."
    },
    {
      "source_id": "SLACK-301",
      "source_type": "slack",
      "timestamp": "2026-10-30T14:04:10Z",
      "author_or_actor": "alice.dev",
      "channel_or_service": "#incidents-prod",
      "summary": "Alice notices checkout latency alert",
      "snippet": "Seeing an alert for checkout latency. Investigating error rates on Stripe webhooks."
    }
  ],
  "unverified_citations": [],
  "retrieved_events": [
    {
      "source_id": "ALERT-201",
      "timestamp": "2026-10-30T14:02:00Z",
      "source_type": "monitoring_alert",
      "summary": "CRITICAL: P99 latency breach on /checkout > 2000ms",
      "score": 0.892
    }
  ]
}
```

#### 7. `/api/investigations` `[PLANNED EXTENSION — Implemented in Frontend Mock/Client]`
To enable saving multi-turn investigation findings, Person 2 introduced client methods `listInvestigations()` and `saveInvestigation()` in `frontend/src/api.ts`:
- **`GET /api/investigations`** -> returns `list[Investigation]`
- **`POST /api/investigations`** -> saves `Investigation` payload
- *Current Status*: Fully functional in `mockApi.ts` using local browser / in-memory state. Backend MongoDB persistence for investigation sessions is planned after Milestone 6.

---

### 6.3 Shared TypeScript Interfaces for Frontend & Mocking

Person 2 (Frontend) uses these exact types in `frontend/src/types/api.ts` and `frontend/src/types/extra.ts`:

```typescript
export type SourceType = 'slack' | 'monitoring_alert' | 'deployment_log';

export interface EventRecord {
  source_id: string;
  incident_id: string;
  timestamp: string; // ISO-8601 UTC
  source_type: SourceType;
  author_or_actor: string;
  channel_or_service: string;
  summary: string;
  raw_content: string;
  structured_payload?: Record<string, any>;
  tags?: string[];
}

export interface CitationRecord {
  source_id: string;
  source_type: SourceType;
  timestamp: string;
  author_or_actor: string;
  channel_or_service: string;
  summary: string;
  snippet: string;
}

export interface TimelineResponse {
  incident_id: string;
  total_events: number;
  filtered_count: number;
  events: EventRecord[];
}

export interface QueryRequest {
  query: string;
  limit?: number;
  start_time?: string | null;
  end_time?: string | null;
}

export interface QueryResponse {
  answer: string;
  citations: CitationRecord[];
  unverified_citations: string[];
  retrieved_events: Array<{
    source_id: string;
    timestamp: string;
    source_type: SourceType;
    summary: string;
    score: number;
  }>;
}

export interface IncidentSummary {
  incident_id: string;
  title: string;
  event_count: number;
  start_time: string;
  end_time: string;
  services_involved: string[];
}

// Multi-turn Investigation Persistence Types (from extra.ts)
export interface InvestigationQuestion {
  query: string;
  answer: string;
  citations: CitationRecord[];
  asked_at: string;
}

export interface Investigation {
  id: string;
  incident_id: string;
  title: string;
  analyst: string;
  is_mine: boolean;
  status: "in_progress" | "completed";
  question_count: number;
  last_activity: string;
  questions: InvestigationQuestion[];
}

export interface IngestResponse {
  incident_id: string;
  ingested_count: number;
  status: string;
}
```

---

## 7. Evaluation Framework & Quality Gates `[PERSON 3]`

### 7.1 Golden Evaluation Benchmark (`data/eval_cases.json`) `[IMPLEMENTED]`
Person 3 has established 6 benchmark evaluation cases covering the full incident investigation lifecycle:
1. **EVAL-001 (First Sign of Trouble)**: Must retrieve and cite `ALERT-201` (Datadog P99 latency breach at 14:02:00Z).
2. **EVAL-002 (Responders & Commander)**: Must cite `SLACK-301` (Alice notices) and `SLACK-302` (Bob declares SEV-1 and acts as IC).
3. **EVAL-003 (Preceding Deployment)**: Must identify `DEPLOY-101` (checkout-service v2.4.1 commit a1f9c8d).
4. **EVAL-004 (Recovery Evidence)**: Must cite `ALERT-205` (P99 latency recovered to 142ms) and `SLACK-307`.
5. **EVAL-005 (Root Cause vs Unproven Hypothesis)**: Must prove pool leak in `db_pool.py` (`SLACK-305`), disprove disk full (`ALERT-203`), and identify Stripe webhook latency as unproven (`SLACK-309`).
6. **EVAL-006 (Negative / Insufficient Evidence)**: Query asking about an expired SSL certificate on ingress must report insufficient evidence and cite zero hallucinated sources.

### 7.2 Retrieval Evaluation Metrics `[PLANNED: DATA-304]`
- **Hit Rate@5**: Must equal 100% across all golden cases.
- **Mean Reciprocal Rank (MRR)**: Target >= 0.85.
- **Retrieval Latency**: P95 retrieval latency < 500ms.
- **Citation Precision**: 100% of generated citations must exist in retrieved context (zero hallucinated citations allowed).

---

## 8. Security, Environment, and Configuration

- All secrets managed via `.env` (never committed to Git).
- Required variables:
  - `MONGODB_URI`: Connection string to MongoDB Atlas.
  - `MONGODB_DB_NAME`: Database name (e.g. `incident_investigator`).
  - `VECTOR_INDEX_NAME`: Atlas Vector Search index name (default `vector_index`). Must match the deployed index exactly; the live demo cluster currently uses `vector-index`.
  - `EMBEDDING_PROVIDER`: `"gemini"` (default) or `"openai"`.
  - `EMBEDDING_API_KEY`: API key for embeddings.
  - `EMBEDDING_MODEL_NAME`: `gemini-embedding-2` (default), `gemini-embedding-001` (supported alternative), or OpenAI `text-embedding-3-small`; all are requested/validated at 1536 dims.
  - `EMBEDDING_DIMENSIONS`: `1536`; must match `backend/atlas_vector_index.json` (`numDimensions`).
  - `LLM_PROVIDER`: `"gemini"` (default) or `"openai"`.
  - `LLM_API_KEY`: API key for LLM.
  - `LLM_MODEL_NAME`: `gemini-3.8-flash` (default, free tier) or OpenAI `gpt-4o-mini`.
  - `LLM_GEMINI_THINKING_LEVEL`: Gemini only; `minimal`, `low` (default), `medium`, or `high`. `none`/`off`/`default` omits thinking config.
  - `LLM_MAX_ATTEMPTS`: Total generation attempts including the first (default `3`; `1` disables retries; max `5`).
  - `LLM_RETRY_BASE_DELAY_SECONDS`: Exponential backoff base (default `0.5`).
  - `LLM_RETRY_MAX_DELAY_SECONDS`: Per-retry backoff cap (default `4.0`).
  - `LLM_REQUEST_DEADLINE_SECONDS`: Hard wall-clock budget for one generation call including retries (default `30.0`).
  - `CORS_ORIGINS`: Allowed origins (e.g. `http://localhost:5173`).
- **Explicit provider selection (no runtime fallback)**: `LLM_PROVIDER` selects answer generation and `EMBEDDING_PROVIDER` selects embeddings independently. The application never switches providers automatically. To move only generation to OpenAI while keeping Gemini embeddings, keep the entire `EMBEDDING_*` block unchanged (`EMBEDDING_PROVIDER=gemini`, Gemini embedding key/model, `EMBEDDING_DIMENSIONS=1536`) so the stored Atlas vectors and `vector-index` definition remain valid, and set `LLM_PROVIDER=openai`, `LLM_API_KEY=<OpenAI API key>`, and `LLM_MODEL_NAME=gpt-4o-mini` (or another OpenAI chat-completions model enabled on the account). The app reads `LLM_API_KEY`, not `OPENAI_API_KEY`. OpenAI API access and billing are separate from a ChatGPT subscription.
