# MongoHack Incident Timeline Investigator

Grounded RAG and deterministic timeline analysis system for post-incident review and active incident triage.

---

## 1. Architecture & Core Principles

- **Deterministic Chronology First**: Event ordering is computed mathematically by sorting ISO-8601 timestamps in Python and MongoDB Atlas—never inferred or altered by LLMs.
- **Strict Grounding & Traceable Citations**: Claims must cite exact event tokens (`[SOURCE_ID]`) programmatically verified against retrieved evidence.
- **Architectural Simplicity**: Clean, idiomatic Python with FastAPI, Pydantic v2, and PyMongo. No opaque agent frameworks (no LangChain, no LangGraph).

---

## 2. Project Layout

```text
backend/
├── app/
│   ├── api/             # FastAPI routes (healthcheck, incidents, timeline, events)
│   ├── core/            # Configuration (pydantic-settings), logging, MongoDB client
│   ├── models/          # Pydantic v2 schemas (EventRecord, TimelineResponse, etc.)
│   ├── services/
│   │   ├── ingestion.py # Ingestion & normalization for Slack, Alerts, and Deployments
│   │   ├── storage.py   # StorageService encapsulating MongoDB Atlas and in-memory fallback
│   │   └── timeline.py  # Pure deterministic sorting, windowing, and filtering functions
│   └── main.py          # FastAPI application factory & lifespan management
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment configuration
tests/                   # Pytest suite
data/
└── incidents/
    └── inc_2026_042.json# Canonical 17-event synthetic incident dataset
```

---

## 3. Setup & Environment Configuration (`uv`)

The project uses [`uv`](https://github.com/astral-sh/uv) for fast, deterministic Python dependency resolution and project environment management.

### Prerequisites
- Python 3.12+
- `uv` (installed via `curl -LsSf https://astral.sh/uv/install.sh` or `pipx install uv`)

### Installation & Environment Setup

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```

2. Sync the project environment and lockfile:
   ```bash
   uv sync
   ```
   This creates/updates the project-local `.venv` using Python 3.12, respecting `uv.lock`.

3. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

   Key configuration variables in `.env`:
   - `MONGODB_URI`: Connection string to MongoDB Atlas (e.g. `mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority`). If left empty, the application automatically falls back to fast in-memory storage for offline development and testing.
   - `MONGODB_DB_NAME`: Database name (default: `incident_investigator`).
   - `CORS_ORIGINS`: Allowed origins (default: `http://localhost:5173,http://127.0.0.1:5173`).
   - `HOST`: Server host (default: `127.0.0.1`).
   - `PORT`: Server port (default: `8000`).

---

## 3.1 MongoDB Atlas Persistent Storage & Indexing (Milestone 2)

The application persists incident events in MongoDB Atlas in the `incident_events` collection, allowing all events to survive application restarts.

### Database Indexes
On startup, `StorageService.create_indexes()` automatically ensures the following indexes are active:
1. **`incident_source_id_unique`** (`{"incident_id": 1, "source_id": 1}`, `unique=True`): Enforces that each event reference (`source_id`) is strictly unique within an incident.
2. **`incident_timestamp_idx`** (`{"incident_id": 1, "timestamp": 1}`): Enables rapid retrieval of incident timelines in deterministic chronological order with start/end time windowing.
3. **`timestamp_idx`** (`{"timestamp": 1}`): Accelerates cross-incident chronological queries.
4. **`source_id_idx`** (`{"source_id": 1}`): Speeds up direct lookups by source identifier.
5. **`source_type_idx`** (`{"source_type": 1}`): Speeds up faceted filtering across evidence types (`slack`, `monitoring_alert`, `deployment_log`).

### Duplicate Event Handling Behavior
- **Intra-batch duplicates**: Batches containing duplicate `source_id`s for the same incident are rejected during schema validation (HTTP 422 Unprocessable Content).
- **Inter-batch / Re-ingestion (Idempotent Upsert)**: Re-ingesting an existing `(incident_id, source_id)` performs an idempotent upsert (`ReplaceOne(..., upsert=True)`). The existing event document is updated with the latest attributes and content in-place without generating duplicate documents or increasing the event count.
- **Database Unique Constraint**: Direct attempts to insert a duplicate `(incident_id, source_id)` violate the unique compound index and raise `DuplicateKeyError`.

### Offline Local Development Fallback
If `MONGODB_URI` is not set or empty in `.env`, the backend automatically falls back to its built-in in-memory storage engine. All endpoints (`/health`, `/ingest`, `/timeline`, `/events`, `/incidents`) remain fully functional for local offline development and testing without requiring Atlas credentials.

### Manual MongoDB Atlas Setup Guide
To connect a live MongoDB Atlas cluster:
1. **Create an Atlas Cluster**: In the [MongoDB Atlas Console](https://cloud.mongodb.com), create a free M0 or higher cluster.
2. **Configure Database User**: Go to **Database Access** -> **Add New Database User**. Choose Password authentication and assign the user `readWrite` access to the `incident_investigator` database.
3. **Configure Network Access**: Go to **Network Access** -> **Add IP Address**. Add your development machine's public IP address (or `0.0.0.0/0` with appropriate authentication for sandbox development).
4. **Set Connection String**: Copy the SRV connection URI from **Database** -> **Connect** -> **Drivers** and set it in `backend/.env`:
   ```bash
   MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
   MONGODB_DB_NAME=incident_investigator
   ```
5. **Atlas Vector Search Index (for upcoming Vector Search milestone)**:
   In Atlas UI, navigate to **Database** -> **Search Indexes** -> **Create Search Index** -> **Atlas Vector Search (JSON Editor)**.
   - Database: `incident_investigator`
   - Collection: `incident_events`
   - Index Name: `vector_index`
   - Definition:
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

---

## 4. Running the Backend

Start the development server using `uv run`:
```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

The API will start at `http://127.0.0.1:8000`. On startup, if storage is empty, it automatically pre-populates demo incident `INC-2026-042` from `data/incidents/inc_2026_042.json`.

---

## 5. Running Tests

Run the complete test suite with `uv run`:

```bash
# Inside backend/:
cd backend
uv run pytest tests/ -v

# Or from project root:
uv run --project backend pytest tests/ -v
```

The test suite covers:
- Backend startup and API health status.
- Security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP).
- Normalization of heterogeneous sources (Slack, Datadog/CloudWatch alerts, deployment logs).
- UTC timestamp conversion and ISO-8601 validation.
- Deterministic chronological sorting under randomized input order.
- Inclusive date-window filtering and multi-source type filtering.
- Handling of missing fields, malformed timestamps, and duplicate source IDs.
- API error contracts (404 for unknown incidents/events, 422 for malformed parameters).

---

## 6. Available API Endpoints

### 1. `GET /api/health`
Checks API and database status.
```json
{
  "status": "ok",
  "database": "connected",
  "version": "1.0.0"
}
```

### 2. `POST /api/incidents/ingest`
Ingests a batch of raw or canonical incident events.
- **Request**:
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
      "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold..."
    }
  ]
}
```
- **Response** (`201 Created`):
```json
{
  "incident_id": "INC-2026-042",
  "ingested_count": 1,
  "status": "success"
}
```

### 3. `GET /api/incidents`
Lists all recorded incidents with chronological boundaries.
- **Response** (`200 OK`):
```json
[
  {
    "incident_id": "INC-2026-042",
    "title": "Bob declares SEV-1 incident INC-2026-042 and steps up as Incident Commander",
    "event_count": 17,
    "start_time": "2026-10-30T13:45:00Z",
    "end_time": "2026-10-30T14:45:00Z",
    "services_involved": [
      "#deployments",
      "#incidents-prod",
      "checkout-service",
      "postgres-db-primary"
    ]
  }
]
```

### 4. `GET /api/incidents/{incident_id}/timeline`
Fetches deterministically ordered events for an incident with optional filters.
- **Query Parameters**:
  - `start_time` (optional): Earliest ISO-8601 UTC timestamp (inclusive).
  - `end_time` (optional): Latest ISO-8601 UTC timestamp (inclusive).
  - `source_type` (optional): Comma-separated list (`slack,monitoring_alert,deployment_log`).
- **Response** (`200 OK`):
```json
{
  "incident_id": "INC-2026-042",
  "total_events": 17,
  "filtered_count": 2,
  "events": [
    {
      "source_id": "DEPLOY-101",
      "incident_id": "INC-2026-042",
      "timestamp": "2026-10-30T13:45:00Z",
      "source_type": "deployment_log",
      "author_or_actor": "devops-bot",
      "channel_or_service": "checkout-service",
      "summary": "Deployment of checkout-service v2.4.1 to production",
      "raw_content": "DEPLOYMENT SUCCESSFUL: checkout-service v2.4.1 deployed to cluster prod-us-east-1...",
      "structured_payload": {"version": "v2.4.1", "commit": "a1f9c8d"},
      "tags": ["deployment", "release"]
    }
  ]
}
```

### 5. `GET /api/incidents/{incident_id}/events/{source_id}`
Retrieves full details and raw structured payload for a single event.
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
  "raw_content": "CRITICAL: checkout-service P99 latency exceeded 2000ms threshold (measured: 2840ms)...",
  "structured_payload": {
    "metric": "p99_latency_ms",
    "threshold": 2000,
    "measured_value": 2840,
    "severity": "CRITICAL"
  },
  "tags": ["alert", "latency", "critical", "checkout"]
}
```


---

## 7. Testing & Evaluation

The repository includes a comprehensive 2-tier testing and evaluation harness validating ingestion integrity, retrieval recall, citation fidelity, and edge-case traps.

### 7.1 Ingestion Validation (`validate_ingestion.py`)
Validates that heterogeneous raw sources are normalized, chunked, and stored with zero data loss.

```bash
# Run in offline mode (validates on local JSON/text dumps)
python validate_ingestion.py --offline

# Or against a live MongoDB Atlas cluster (when MONGODB_URI is set)
python validate_ingestion.py
```

**Validation Checks (8/8 Pass):**
1. **Mandatory Fields & Unique IDs:** Every event has `event_id`, `timestamp_utc`, `source_type`, and `raw_ref` with 100% unique IDs.
2. **UTC Conversion:** Server EDT (`09:40:00 EDT`), Alert IST (`19:37:00+05:30`), and Slack epoch timestamps match hand-computed UTC.
3. **Zero-Loss Count Reconciliation:** 62 raw records -> 62 normalized events -> 32 chunks with zero events lost.
4. **Referential Integrity:** Every `chunk.event_ids` entry exists in the normalized events collection.
5. **Window Limits:** All chat conversation chunks obey <= 10 messages and <= 10 minutes span.
6. **Deduplication:** Re-import of the same file is caught and rejected by SHA-256 `file_hash`.
7. **Secret Redaction:** Fake token `xoxb-FAKE-0000-TEST` is safely masked as `[REDACTED_SECRET]` in all stored text.
8. **Conflict Preservation:** Both the 14:02 chat claim and 14:07 alert timestamp are preserved in `raw_ref`.

---

### 7.2 Benchmark Evaluation Suite (`eval/run_tests.py`)
Runs 13 automated Pytest regression tests against the 10 benchmark cases in `eval/eval_cases.json`:

```bash
# Run all evaluation tests via pytest
python eval/run_tests.py
# or
pytest eval/tests/ -v
```

**Evaluated Criteria (13/13 Pass):**
- **Recall@5 & Mean Recall:** Asserts high retrieval recall on all ground-truth target event IDs across answerable cases.
- **Citation Accuracy:** Verifies all cited event IDs exist in the retrieved candidate set, and all quoted timestamps match stored values.
- **Refusal Correctness:** Refuses unanswerable cases (`EVAL-009` DB migration, `EVAL-010` inventory-sync alert gap) with zero false refusals on valid queries.
- **Filter Isolation:** Asserts zero leakage from last month's distractor (`incident_000`) or out-of-window events.
- **Deterministic Ordering:** Verifies timeline is strictly sorted ascending by UTC timestamp.
- **Conflict Surfacing:** Verifies timestamp discrepancies are explicitly highlighted.
- **Actor Traps:** Distinguishes actual operational actors (`dave.ops` ack, `elena.dev` rollback) from @mentioned colleagues.
- **Security Redaction:** Verifies secret tokens never appear in answers or timeline records.

---

### 7.3 Demo & Database Seeding (`demo/seed.py`)
Loads `incident_001` and `incident_000` into database storage and checks Atlas Vector Search index readiness before demo execution:

```bash
# Seed in offline mode
python demo/seed.py --offline

# Or seed live MongoDB Atlas and poll for Vector Search readiness
python demo/seed.py --uri "<MONGODB_URI>"
```

See [`demo/demo_script.md`](demo/demo_script.md) for the 7-minute live presentation walkthrough and [`demo/ppt_eval_slide.md`](demo/ppt_eval_slide.md) for presentation slide content.
