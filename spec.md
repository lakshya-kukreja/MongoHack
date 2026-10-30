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

3. **Backend Citation Validation & Structure**:
   The response undergoes programmatic validation:
   - Regex extraction of all `\\[([A-Z]+-\\d+)\\]` tags in the generated answer.
   - Cross-check against the set of `source_id`s in the retrieved context documents.
   - If an unverified source ID is found, it is stripped from citations and returned in `unverified_citations`.
   - Return structured citation objects alongside the text:
     ```json
     {
       "answer": "The initial alert triggered at 14:02:00Z when checkout latency spiked to 2840ms [ALERT-201]. Alice first acknowledged this in Slack four minutes later [SLACK-301].",
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
           "summary": "Alice acknowledges checkout errors",
           "snippet": "Seeing an alert for checkout latency. Investigating error rates on Stripe webhooks and checkout endpoint."
         }
       ],
       "unverified_citations": []
     }
     ```

4. **Frontend Interaction**:
   - The UI replaces `[ALERT-201]` tokens with an interactive clickable badge `<CitationChip id="ALERT-201" />`.
   - Clicking the badge scrolls to and highlights that record on the timeline and/or opens the Event Inspector Drawer with full raw details and payload metrics.

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

### 4.3 Deterministic Timeline Query Pattern & Date-Filtering Behavior
When rendering the incident chronology, vector search is **not** used. Instead, standard indexed sorting guarantees chronological truth:

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

## 6. REST API Endpoints Specification & Frontend Contract

### 6.1 Endpoints Overview

| Method | Endpoint | Description | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/health` | Healthcheck & DB status | None | `HealthResponse` |
| `POST` | `/api/incidents/ingest` | Ingest JSON array of incident records | `IngestRequest` | `IngestResponse` |
| `GET` | `/api/incidents` | List all available incidents with summary | None | `list[IncidentSummary]` |
| `GET` | `/api/incidents/{incident_id}/timeline` | Fetch deterministic chronological timeline | Query params: `start_time`, `end_time`, `source_type` | `TimelineResponse` |
| `POST` | `/api/incidents/{incident_id}/query` | Ask an investigation question (RAG) | `QueryRequest` | `QueryResponse` |
| `GET` | `/api/incidents/{incident_id}/events/{source_id}` | Retrieve single event detail | Path params | `EventRecord` |

---

### 6.2 Detailed Request & Response Formats

#### 1. `GET /api/health`
- **Response** (`200 OK`):
```json
{
  "status": "ok",
  "database": "connected",
  "version": "1.0.0"
}
```

#### 2. `POST /api/incidents/ingest`
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
  "ingested_count": 18,
  "status": "success"
}
```

#### 3. `GET /api/incidents`
- **Response** (`200 OK`):
```json
[
  {
    "incident_id": "INC-2026-042",
    "title": "Payment Gateway P99 Latency Spike & Cascading Connection Pool Exhaustion",
    "event_count": 18,
    "start_time": "2026-10-30T13:45:00Z",
    "end_time": "2026-10-30T14:45:00Z",
    "services_involved": ["checkout-service", "postgres-db-primary"]
  }
]
```

#### 4. `GET /api/incidents/{incident_id}/timeline`
- **Query Parameters**:
  - `start_time` (string, optional): ISO-8601 string (e.g., `2026-10-30T14:00:00Z`).
  - `end_time` (string, optional): ISO-8601 string (e.g., `2026-10-30T14:30:00Z`).
  - `source_type` (string, optional): Comma-delimited list of source types (e.g., `slack,monitoring_alert`).
- **Response** (`200 OK`):
```json
{
  "incident_id": "INC-2026-042",
  "total_events": 18,
  "filtered_count": 18,
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

#### 5. `POST /api/incidents/{incident_id}/query`
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

#### 6. `GET /api/incidents/{incident_id}/events/{source_id}`
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

---

### 6.3 Shared TypeScript Interfaces for Frontend & Mocking

Person 2 (Frontend) can use these exact types in `frontend/src/types/api.ts`:

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
```

#### Parallel Development via Mock Service Worker / Local Mocks:
Person 2 does not need to wait for backend deployment. The frontend can initialize `frontend/src/mocks/mockApi.ts` using the bundled demo data [`data/incidents/inc_2026_042.json`](file:///home/asus/MongoHack/data/incidents/inc_2026_042.json) to develop and verify all components immediately.

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

