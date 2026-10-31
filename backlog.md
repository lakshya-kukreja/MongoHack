# Project Backlog & Implementation Milestones

## 1. Executive Status Dashboard

| Task ID | Task Name | Owner | Status | Dependencies | Verification Command / Target |
|---|---|---|---|---|---|
| **CORE-001** | Architecture, 3-Person Ownership & Spec Synchronization | Shared (P1/P2/P3) | **DONE** | None | Inspection of `AGENTS.md`, `spec.md`, `backlog.md` |
| **BE-101** | Backend Scaffolding, Virtualenv, Settings & Health API | Person 1 | **DONE** | None | `backend/.venv/bin/pytest tests/test_health.py -v` (4 passed) |
| **BE-102** | Canonical Event Schema & Heterogeneous Ingestion Engine | Person 1 | **DONE** | BE-101 | `backend/.venv/bin/pytest tests/test_ingestion.py -v` (11 passed) |
| **BE-103** | MongoDB Atlas Storage Layer & Index Management | Person 1 | **DONE** | BE-102 | `backend/.venv/bin/pytest tests/test_storage*.py -v` (9 passed) |
| **BE-104** | Deterministic Timeline Engine (Sorting & Windowing) | Person 1 | **DONE** | BE-103 | `backend/.venv/bin/pytest tests/test_timeline.py -v` (9 passed) |
| **BE-105** | Core REST API Endpoints (Ingest, Timeline, Events, List) | Person 1 | **DONE** | BE-103, BE-104 | `backend/.venv/bin/pytest tests/test_api*.py -v` (14 passed) |
| **BE-106** | Vector Embedding Generation Service (`embeddings.py`) | Person 1 | **DONE** | BE-102 | `backend/.venv/bin/pytest tests/test_embeddings.py -v` (31 passed) |
| **BE-106B** | Embedding Provider Error, Timeout & Rate-Limit Resilience | Person 1 | **PENDING** | BE-106 | Timeout & retry tests in `test_embeddings.py` |
| **BE-106C** | Attach Embeddings to Ingested Events Before Storage | Person 1 | **DONE** | BE-103, BE-106 | Ingestion/storage integration tests with mocked provider |
| **BE-107** | MongoDB Atlas `$vectorSearch` Retrieval Service (`retrieval.py`) | Person 1 | **DONE** | BE-103, BE-106 | `backend/.venv/bin/pytest tests/test_retrieval.py -v` |
| **BE-108** | Grounded LLM Generation Engine (`generator.py`) | Person 1 | **DONE** | BE-107 | Context formulation & prompt tests in `test_generator.py` |
| **BE-108B** | Citation Post-Processing & Validation against Retrieved IDs | Person 1 | **PENDING** | BE-108 | Regex validation tests in `tests/test_generator.py` |
| **BE-108C** | Insufficient & Contradictory Evidence Handler | Person 1 | **PENDING** | BE-108 | Negative tests verifying standard refusal phrase |
| **BE-108D** | LLM Provider Error, Timeout & Rate-Limit Resilience | Person 1 | **PENDING** | BE-108 | Timeout (504) and rate-limit (503) tests |
| **BE-109** | Investigation Query Endpoint (`POST /api/incidents/{id}/query`) | Person 1 | **DONE** | BE-105, BE-108 | `backend/.venv/bin/pytest tests/test_api_query.py -v` |
| **BE-110** | Unit Test Suite with Mocked Embedding and LLM Calls | Person 1 | **PENDING** | BE-106, BE-108 | `backend/.venv/bin/pytest tests/ -v` (100% offline) |
| **BE-111** | End-to-End RAG Integration Tests & Reproducible Demo Script | Person 1 | **PENDING** | BE-109, BE-110 | `python scripts/demo_rag.py` |
| **BE-112** | Idempotent embedding backfill for already-ingested Atlas events | Person 1 | **DONE** | BE-106C, OPS-002 | Offline mocked tests + explicit CLI backfill command; live backfill pending operator approval |
| **BE-113** | Migrate embeddings and answer generation to Google Gemini (1536-dim) | Person 1 | **DONE** | BE-106, BE-108, BE-112 | Offline tests: `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py tests/test_embedding_backfill.py -v` (58 passed); full suite 110 passed |
| **BE-114** | Verify Gemini `gemini-embedding-001` and generation API compatibility | Person 1 | **SUPERSEDED by BE-115** | BE-113 | Offline tests: `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py -v` (52 passed); full suite 115 passed |
| **BE-115** | Fix Gemini `batchEmbedContents` dimension flag (nested config ignored → 3072 response) | Person 1 | **DONE** | BE-114 | `backend/.venv/bin/pytest tests/test_embeddings.py -v` (41 passed); full suite 116 passed |
| **BE-116** | Live re-validation of Gemini 1536-dim backfill after BE-115 | Person 1 | **DONE** | BE-115, operator approval | Read-only audit: 17/17 docs at 1536 dims; index `vector-index` READY |
| **BE-117** | Fix empty RAG retrieval: `$vectorSearch` index name mismatch | Person 1 | **DONE** | BE-107, OPS-002 | `backend/.venv/bin/pytest tests/test_retrieval.py -v` (12 passed); full suite 128 passed |
| **BE-118** | Diagnose generic 503 from live RAG query; preserve safe provider diagnostics | Person 1 | **DONE** | BE-109, BE-117 | `backend/.venv/bin/pytest tests/test_generator.py tests/test_api_query.py -v` (35 passed); full suite 146 passed |
| **BE-119** | Investigate confirmed live Gemini generation timeout (30s) | Person 1 | **DONE** | BE-118, OPS-003 | `backend/.venv/bin/pytest tests/test_generator.py tests/test_api_query.py -q` (42 passed); full suite 153 passed |
| **BE-120** | Avoid blocking the async query endpoint during synchronous RAG generation | Person 1 | **PENDING** | BE-119 | `async def` route calls sync `Generator.query()`; move to threadpool or async client |
| **BE-121** | Configure/reuse LLM HTTP client and timeout (only after phase evidence) | Person 1 | **BLOCKED (OPS-004)** | BE-119 | Add configurable timeout / persistent client only if logs justify it |
| **BE-122** | Audit read-phase Gemini generation request against official docs; find non-billable access check | Person 1 | **DONE** | BE-119, OPS-004 | Offline docs audit complete; request shape matches docs; `models.get` confirmed non-billable access check |
| **BE-123** | Harden Gemini generation path: `thinkingLevel`, bounded retries, request deadline | Person 1 | **DONE** | BE-122, OPS-005 | `pytest tests/test_generator.py -q` (45 passed); full suite 166 passed; compileall clean. Live 503 remains a provider-availability blocker |
| **BE-124** | Evaluate explicit OpenAI LLM provider switch while retaining Gemini embeddings | Person 1 | **DONE** | BE-123 | Configuration-only switch; `pytest tests/ -q` (166 passed); compileall clean; no code changes required |
| **FE-201** | Frontend Scaffolding, TanStack Router & Tailwind CSS | Person 2 | **DONE (branch)** | None | Inspect `origin/frontend:frontend/package.json` |
| **FE-202** | Shared Types & Offline Mock API Layer (`mockApi.ts`) | Person 2 | **DONE (branch)** | FE-201, DATA-301 | Inspect `origin/frontend:frontend/src/mocks/` |
| **FE-203** | Deterministic Timeline UI with Time/Type Filters | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/TimelineView.tsx` |
| **FE-204** | Investigation Chat with Grounded Citations & Quick Prompts | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/ChatInterface.tsx` |
| **FE-205** | Event Detail Slide-Over Drawer (`EventDrawer.tsx`) | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/EventDrawer.tsx` |
| **FE-206** | Dashboard & Incident JSON Import Views | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/routes/` |
| **FE-207** | Frontend Test Suite Execution & Component Tests | Person 2 | **IN PROGRESS** | FE-203, FE-204 | `npm test` on frontend branch |
| **FE-208** | Live Backend API Integration (`VITE_USE_MOCK=false`) | Person 2 | **BLOCKED** | BE-109, Branch Merge | Query live port 8000 from frontend client |
| **DATA-301** | Synthetic Golden Incident Dataset (`INC-2026-042`) | Person 3 | **DONE** | None | `data/incidents/inc_2026_042.json` (17 events verified) |
| **DATA-302** | Evaluation Benchmark Definition (`data/eval_cases.json`) | Person 3 | **DONE** | DATA-301 | `data/eval_cases.json` (6 golden queries verified) |
| **DATA-303** | Automated Retrieval Evaluation Harness | Person 3 | **PENDING** | DATA-302, BE-107 | `backend/.venv/bin/pytest tests/test_retrieval_eval.py -v` |
| **DATA-304** | Benchmark Metrics Reporting (Hit Rate@K, MRR, Latency) | Person 3 | **PENDING** | DATA-303 | `python scripts/run_eval.py` output table |
| **DATA-305** | Contradictory & Insufficient Evidence Scenarios | Person 3 | **PENDING** | DATA-302 | Negative & contradictory test cases in eval suite |
| **DATA-306** | Generation Grounding & Citation Correctness Benchmark | Person 3 | **PENDING** | BE-108, DATA-303 | Citation validation score > 95% |
| **OPS-001** | Verify live MongoDB Atlas database/collection/persistence (read-only audit) | Shared (P1) | **DONE** | BE-103, BE-105 | Findings recorded below: Atlas reachable, `incident_investigator.incident_events` absent; no writes performed |
| **OPS-002** | Populate Atlas `incident_investigator.incident_events` via existing ingestion path | Person 1 | **PENDING (needs approval)** | OPS-001 | Creates DB/collection + 17 seed docs; run existing `POST /api/incidents/ingest` or app startup |
| **OPS-003** | Live-verify Gemini credentials/quota and confirm the real RAG query cause | Person 1 | **PENDING (operator-run)** | BE-118 | One `POST /api/incidents/INC-2026-042/query` after BE-118; read the new safe log fields (`status_code`, `error_category`, `provider_status`) and resolve the upstream cause |
| **OPS-004** | Capture live generation timeout phase (`connect`/`read`/`write`/`pool`) | Person 1 | **PENDING (operator-run)** | BE-119 | One live query after BE-119; read `timeout_phase` in the 504 log line, then decide whether a timeout change is justified |
| **OPS-005** | Non-billable `models.get` access check for `gemini-3.8-flash` | Person 1 | **PENDING (operator-run)** | BE-122 | `GET /v1beta/models/gemini-3.8-flash` with the existing key; expect 200 + `generateContent` in `supportedGenerationMethods`; no inference, no billing |

---

## 2. Complete RAG Flow Verification Matrix (12 Pillars)

| # | RAG Flow Pillar | Owner | Status | Associated Tasks | Implementation & Code Location | Verification Details & Test Status |
|---|---|---|---|---|---|---|
| **1** | **MongoDB Atlas persistence and incident ingestion** | Person 1 | **DONE** | `BE-102`, `BE-103`, `BE-105` | [`backend/app/services/storage.py`](file:///home/asus/MongoHack/backend/app/services/storage.py), [`ingestion.py`](file:///home/asus/MongoHack/backend/app/services/ingestion.py), [`db.py`](file:///home/asus/MongoHack/backend/app/core/db.py), [`incidents.py`](file:///home/asus/MongoHack/backend/app/api/incidents.py) | **Verified**: 47 unit/integration tests pass (`tests/test_ingestion.py`, `tests/test_storage*.py`, `tests/test_api*.py`). |
| **2** | **Embedding model/provider configuration and embedding generation** | Person 1 | **DONE** | `BE-106`, `BE-113` | Settings configured in [`config.py`](file:///home/asus/MongoHack/backend/app/core/config.py) (`EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSIONS`). Implemented in [`backend/app/services/embeddings.py`](file:///home/asus/MongoHack/backend/app/services/embeddings.py). | **Verified**: 110 offline tests pass overall; Gemini `gemini-embedding-2` at 1536 dims is the default, OpenAI `text-embedding-3-small` remains supported. |
| **3** | **Semantic vector retrieval with metadata filters** | Person 1 | **DONE** | `BE-107`, `BE-117` | [`backend/app/services/retrieval.py`](file:///home/asus/MongoHack/backend/app/services/retrieval.py), [`backend/atlas_vector_index.json`](file:///home/asus/MongoHack/backend/atlas_vector_index.json), `VECTOR_INDEX_NAME` in [`config.py`](file:///home/asus/MongoHack/backend/app/core/config.py). | **Verified**: `$vectorSearch` pipeline with `incident_id` pre-filter, time/source filters, `$meta` score projection, and `EventRecord` mapping covered by `tests/test_retrieval.py` (12 passed). Live read-only retrieval returned 5 events from `INC-2026-042`; a missing index now raises `VectorIndexNotFoundError` instead of silently returning `[]`. |
| **4** | **LLM provider/model configuration through environment variables** | Person 1 | **IN PROGRESS** | `BE-101`, `BE-108` | Config schema defined in [`config.py`](file:///home/asus/MongoHack/backend/app/core/config.py) (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL_NAME`) and [`backend/.env.example`](file:///home/asus/MongoHack/backend/.env.example). | **In Progress**: Pydantic settings load env vars properly; runtime provider initialization and fallback logic pending `generator.py`. |
| **5** | **Grounded answer generation using retrieved incident evidence** | Person 1 | **PENDING** | `BE-108` | Prompt formulation, context assembly (`[EVIDENCE RECORD <source_id>]`), and direct API calls planned in `backend/app/services/generator.py`. | **Pending implementation**: Generator service module not yet created. |
| **6** | **Source-level citations validated against retrieved event IDs** | Person 1 | **PENDING** | `BE-108B` | Specification detailed in [`spec.md`](file:///home/asus/MongoHack/spec.md#32-citation-contract). Regex post-processor planned in `generator.py`. (Simulated in frontend `mockApi.ts`). | **Pending backend implementation**: Regex citation extraction and programmatic rejection into `unverified_citations` pending. |
| **7** | **Insufficient-evidence handling, without fabricated incident details** | Person 1 | **PENDING** | `BE-108C`, `DATA-302` | Contract defined in `spec.md`; golden test case `EVAL-006` defined in [`data/eval_cases.json`](file:///home/asus/MongoHack/data/eval_cases.json). (Simulated in `mockApi.ts`). | **Pending backend implementation**: Generator fallback to deterministic phrase `"Based on the retrieved incident records, there is insufficient evidence to answer this question."` pending. |
| **8** | **Provider errors, timeouts, and invalid response handling** | Person 1 | **PENDING** | `BE-106B`, `BE-108D` | Contract clarified in `spec.md` (timeouts -> HTTP 504; 429/5xx -> HTTP 503). | **Pending implementation**: Client-level timeout configs and exception handling wrappers pending in `embeddings.py` and `generator.py`. |
| **9** | **Unit tests with mocked embedding/LLM calls** | Person 1 | **PENDING** | `BE-110` | Planned in `tests/test_embeddings.py` and `tests/test_generator.py` using deterministic mock providers. | **Pending implementation**: Mock mongo fixtures exist in `tests/mock_mongo.py`, but mock embedding/LLM test suites are not yet written. |
| **10** | **End-to-end integration tests and reproducible demo with real credentials** | Person 1 | **PENDING** | `BE-111` | Planned in `tests/test_rag_e2e.py` and demonstration CLI in `scripts/demo_rag.py`. | **Pending implementation**: Depends on `BE-109`. |
| **11** | **Retrieval and answer-quality evaluation, coordinated with Person 3** | Person 3 | **PENDING** | `DATA-302`, `DATA-303`, `DATA-304` | 6 golden cases created in `data/eval_cases.json`. Eval harness planned in `tests/test_retrieval_eval.py` and `scripts/run_eval.py`. | **Partially complete**: Dataset and cases complete (`DATA-301`, `DATA-302`); evaluation harness and metric calculation pending `BE-107`. |
| **12** | **Frontend API contract for displaying answers and citations, coordinated with Person 2** | Person 2 / Person 1 | **IN PROGRESS (Frontend DONE / Integration BLOCKED)** | `FE-202`, `FE-204`, `FE-208`, `BE-109` | Contract defined in `spec.md`. Client UI implemented on `origin/frontend` (`ChatInterface.tsx`, `CitationChip.tsx`, `types/api.ts`). | **Blocked**: Frontend ready on mock API; backend endpoint `POST /api/incidents/{incident_id}/query` pending on `backend-dev`. |

---

## 3. Shared Tasks (All Roles)

### Task CORE-001: Architecture, 3-Person Team Ownership & Spec Synchronization
- **Primary Owner**: Shared (Person 1, Person 2, Person 3)
- **Status**: **DONE**
- **Dependencies**: None
- **Scope**:
  - Update `AGENTS.md` with explicit 3-person ownership, file boundaries, collaboration rules, and branch guidelines.
  - Update `spec.md` to clearly distinguish implemented functionality from planned functionality, reconcile dataset event counts (17 events in `INC-2026-042`), and document the frontend `/investigations` session model.
  - Establish mandatory incremental backlog update rules in `backlog.md` with unique task IDs, owners, statuses, dependencies, and verification commands.
- **Acceptance Criteria**:
  - [x] Current working tree and branch (`backend-dev`) verified clean without unauthorized git actions.
  - [x] `AGENTS.md` reflects three-person roles and file ownership boundaries.
  - [x] `spec.md` cleanly separates implemented backend/frontend capabilities from upcoming RAG and eval components.
  - [x] `backlog.md` contains granular tasks with verified statuses, verification commands, and active task tracking.
- **Verification Command**:
  - Inspect `AGENTS.md`, `spec.md`, and `backlog.md` for consistency.

---

## 4. Person 1 — Backend and RAG

### Task BE-101: Backend Scaffolding, Virtualenv, Settings & Health API
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: None
- **Scope**:
  - Setup FastAPI application factory in `backend/app/main.py`.
  - Configure environment settings via `pydantic-settings` in `backend/app/core/config.py`.
  - Add structured logging in `backend/app/core/logging.py`.
  - Implement `/api/health` checking service and database connectivity.
  - Configure `.env.example`, `.gitignore`, and `pytest.ini`.
- **Acceptance Criteria**:
  - [x] `GET /api/health` returns `200 OK` with `{"status": "ok", "database": ...}`.
  - [x] Security headers and CORS middleware registered.
  - [x] Tests in `tests/test_health.py` pass.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_health.py -v` (4 passed).

### Task BE-102: Canonical Event Schema & Heterogeneous Ingestion Engine
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-101
- **Scope**:
  - Define `EventRecord`, `SourceType`, `TimelineResponse`, `IncidentSummary`, `IngestRequest`, `IngestResponse` in `backend/app/models/event.py`.
  - Implement `parse_incident_data` and normalization logic in `backend/app/services/ingestion.py` for Slack, alerts, and deployments.
  - Enforce UTC ISO-8601 timestamps and canonical `embedding_text` construction.
- **Acceptance Criteria**:
  - [x] Ingestion parser handles raw Slack, Datadog alerts, and CI/CD deploy logs.
  - [x] Enforces unique `source_id` within an incident batch.
  - [x] Rejects malformed dates, missing required fields, or invalid schemas with descriptive errors.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_ingestion.py -v` (11 passed).

### Task BE-103: MongoDB Atlas Storage Layer & Index Management
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-102
- **Scope**:
  - Implement `StorageService` in `backend/app/services/storage.py`.
  - Manage database connectivity in `backend/app/core/db.py` with mock/in-memory fallback (`tests/mock_mongo.py`) for offline CI.
  - Ensure unique compound index on `(incident_id, source_id)` and secondary index on `(incident_id, timestamp)`.
  - Export Atlas Vector Search index definition in `backend/atlas_vector_index.json`.
- **Acceptance Criteria**:
  - [x] `insert_events()`, `get_event()`, `get_all_incident_events()`, `list_incidents()` implemented and tested.
  - [x] Idempotent re-ingestion: duplicate `source_id` within the same incident updates/ignores without crashing.
  - [x] Aggregation pipeline computes accurate start time, end time, and service list per incident.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_storage.py tests/test_storage_mongo.py -v` (9 passed).

### Task BE-104: Deterministic Timeline Engine
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-103
- **Scope**:
  - Implement deterministic timestamp sorting and filtering in `backend/app/services/timeline.py`.
  - Enforce inclusive time-window filtering (`start_time <= event <= end_time`).
  - Implement source type filtering (e.g. `slack,monitoring_alert`).
- **Acceptance Criteria**:
  - [x] Events are guaranteed 100% chronologically ordered ascending regardless of ingestion sequence.
  - [x] Inclusive time boundaries accurately filter records.
  - [x] Returns structured `TimelineResponse` matching `spec.md`.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_timeline.py -v` (9 passed).

### Task BE-105: Core REST API Endpoints
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-103, BE-104
- **Scope**:
  - Implement FastAPI router in `backend/app/api/incidents.py`:
    - `POST /api/incidents/ingest`: Batch ingestion of events.
    - `GET /api/incidents`: Incident list and summary cards.
    - `GET /api/incidents/{incident_id}/timeline`: Deterministic chronological timeline.
    - `GET /api/incidents/{incident_id}/events/{source_id}`: Deep event inspection.
  - Add comprehensive parameter validation and HTTP 404 / 422 error handlers.
- **Acceptance Criteria**:
  - [x] All 4 endpoints return schemas strictly matching `spec.md`.
  - [x] Validated against in-memory mock client and PyMongo integration.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_api.py tests/test_api_mongo.py -v` (14 passed).

### Task BE-106: Vector Embedding Generation Service (`embeddings.py`)
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-102
- **Scope**:
  - Create `backend/app/services/embeddings.py`.
  - Integrate with OpenAI (`text-embedding-3-small`, 1536 dims) or Gemini using direct HTTP calls through `httpx` (no provider SDK is installed in the project). Gemini defaults were later migrated to `gemini-embedding-2` at 1536 dims in BE-113.
  - Support single text, batch generation (`generate_embeddings_batch(texts)`), and event embedding from canonical `embedding_text`.
  - Validate inputs, provider responses, vector count, numeric finiteness, and model dimensions; raise explicit exceptions instead of returning fake vectors.
- **Acceptance Criteria**:
  - [x] `generate_embedding(text: str) -> list[float]` returns valid float vector.
  - [x] `generate_embeddings_batch(texts: list[str]) -> list[list[float]]` chunks batches at 64 items by default.
  - [x] Deterministic mock providers are injected in offline unit tests without network access or real credentials.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py -v` (31 passed).

### Task BE-106B: Embedding Provider Error, Timeout & Rate-Limit Resilience
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-106
- **Scope**:
  - Reuse the 10-second embedding timeout and provider exceptions implemented in BE-106.
  - Implement exponential backoff for HTTP 429 rate limits.
  - Map fatal upstream errors to `HTTPException(503, "Embedding provider unavailable")` and timeouts to `HTTPException(504, "Embedding provider timed out")` at the API integration layer.
- **Acceptance Criteria**:
  - [ ] Tests simulate timeout, rate limit, and retry exhaustion; verify proper status codes and error messages.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py -k "timeout or error" -v`

### Task BE-106C: Attach Embeddings to Ingested Events Before Storage
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-103, BE-106
- **Scope**:
  - Wire `generate_event_embeddings()` into the ingestion/storage path once provider configuration is available.
  - Preserve existing ingestion and storage behavior when embeddings are disabled or unavailable.
  - Keep provider calls mockable for 100% offline tests.
- **Acceptance Criteria**:
  - [ ] Ingested events persist a non-empty `embedding` vector matching the configured model dimension.
  - [ ] Ingestion tests use a mocked provider and do not require network access.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_ingestion.py tests/test_storage*.py -v`

### Task BE-107: MongoDB Atlas `$vectorSearch` Retrieval Service (`retrieval.py`)
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-103, BE-106
- **Scope**:
  - Create `backend/app/services/retrieval.py`.
  - Construct `$vectorSearch` pipeline pre-filtered by `incident_id` and optional time range.
  - Project search score (`$meta: "vectorSearchScore"`) and return ranked evidence candidates.
- **Acceptance Criteria**:
  - [ ] Query vector matches against collection index `vector_index`.
  - [ ] Pre-filter strictly isolates results to target `incident_id`.
  - [ ] Returns candidate records with relevance scores.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_retrieval.py -v`

### Task BE-108: Grounded LLM Generation Engine (`generator.py`)
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-107
- **Scope**:
  - Create `backend/app/services/generator.py`.
  - Construct prompt with system instructions enforcing strict evidence grounding, `[SOURCE_ID]` citation tokens, and uncertainty handling.
  - Format context with explicit `[EVIDENCE RECORD <source_id>]` blocks sorted chronologically.
  - Make direct API calls to OpenAI / Gemini without heavy agent frameworks.
- **Acceptance Criteria**:
  - [ ] Generated answers cite retrieved sources directly using `[SOURCE_ID]`.
  - [ ] Context formatting preserves chronological ordering of evidence blocks.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_generator.py -v`

### Task BE-108B: Citation Post-Processing & Validation against Retrieved IDs
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-108
- **Scope**:
  - Implement post-processing citation validator: regex extraction of `\[([A-Z]+-\d+)\]`.
  - Cross-validate extracted tags against retrieved context `source_id`s.
  - Reject hallucinated IDs into `unverified_citations` list.
  - Return structured `CitationRecord` objects (`source_id`, `source_type`, `timestamp`, `author_or_actor`, `channel_or_service`, `summary`, `snippet`).
- **Acceptance Criteria**:
  - [ ] Legitimate citations mapped to structured `CitationRecord`s.
  - [ ] Hallucinated citations stripped from text and reported in `unverified_citations`.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_generator.py -k "citation" -v`

### Task BE-108C: Insufficient & Contradictory Evidence Handler
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-108
- **Scope**:
  - Return exact standard refusal phrase when retrieved evidence is insufficient: `"Based on the retrieved incident records, there is insufficient evidence to answer this question."`.
  - Explicitly surface contradictions when contradictory records are present in retrieved context.
- **Acceptance Criteria**:
  - [ ] Negative queries cite zero sources and return standard insufficient evidence statement.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_generator.py -k "insufficient or contradiction" -v`

### Task BE-108D: LLM Provider Error, Timeout & Rate-Limit Resilience
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-108
- **Scope**:
  - Add 30-second timeout configuration to LLM requests.
  - Map HTTP 429 and 5xx failures to `HTTPException(503, "LLM provider unavailable or rate-limited")`.
  - Map timeouts to `HTTPException(504, "LLM provider timed out")`.
- **Acceptance Criteria**:
  - [ ] Simulated timeouts and rate limits return HTTP 504 / 503 without leaking stack traces.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_generator.py -k "timeout or error" -v`

### Task BE-109: Investigation Query Endpoint
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-105, BE-108, BE-108B, BE-108C
- **Scope**:
  - Implement `POST /api/incidents/{incident_id}/query` in `backend/app/api/incidents.py`.
  - Define `QueryRequest`, `QueryResponse`, and `CitationRecord` models in `backend/app/models/event.py`.
  - Wire embedding -> retrieval -> context assembly -> generation -> citation validation -> `QueryResponse`.
- **Acceptance Criteria**:
  - [ ] Returns `QueryResponse` matching `spec.md` with `answer`, `citations`, `unverified_citations`, `retrieved_events`.
  - [ ] Responds with HTTP 404 if incident does not exist.
  - [ ] Responds with HTTP 422 for malformed requests.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_api_query.py -v`

### Task BE-110: Unit Test Suite with Mocked Embedding and LLM Calls
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-106, BE-108
- **Scope**:
  - Provide `MockEmbeddingProvider` and `MockLLMProvider` in `tests/conftest.py`.
  - Guarantee 100% offline test execution without requiring network access or external credentials.
- **Acceptance Criteria**:
  - [ ] All tests in `tests/` pass with zero internet connectivity.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/ -v`

### Task BE-111: End-to-End RAG Integration Tests & Reproducible Demo Script
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-109, BE-110
- **Scope**:
  - Create integration test `tests/test_rag_e2e.py` testing the complete RAG query lifecycle.
  - Create standalone demonstration CLI script `scripts/demo_rag.py` demonstrating ingestion, embedding, vector retrieval, and grounded citation generation.
- **Acceptance Criteria**:
  - [ ] `scripts/demo_rag.py` runs cleanly against mock or live credentials and prints verified investigation findings.
- **Verification Command**:
  - `python scripts/demo_rag.py`

### Task BE-112: Idempotent Embedding Backfill for Already-Ingested Atlas Events
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-106C, OPS-002
- **Scope**:
  - Audit existing `incident_investigator.incident_events` documents read-only for `embedding` presence/dimensions.
  - Add a safe, idempotent backfill workflow that embeds `embedding_text` via the configured provider and updates only the `embedding` field.
  - Enforce the 1536-dimension contract from `backend/atlas_vector_index.json`; fail clearly on incompatible provider/model dimensions.
  - Never replace `_id`, `source_id`, `incident_id`, timestamps, or other metadata during backfill.
- **Audit Findings (read-only, 2026-10-31)**:
  - `incident_investigator.incident_events`: 17 documents, all for `INC-2026-042`.
  - `missing_or_null_embedding=17`, `documents_with_non_empty_embedding=0`, dimension distribution `{NoneType: 17}`.
  - `embedding_text` is present on all 17 documents, so backfill can proceed without re-ingestion.
  - `list_search_indexes()` returned `[]`: the `vector_index` search index does **not** exist yet.
- **Implementation**:
  - `backend/app/services/embeddings.py`: added `EmbeddingDimensionError` and `validate_embedding_dimension()`.
  - `backend/app/services/storage.py`: added targeted `get_event_documents()` and `update_event_embedding()` (uses `$set` only; preserves `_id`/metadata).
  - `backend/app/services/embedding_backfill.py`: `EmbeddingBackfillService` with `missing` (default), `invalid`, and `all` modes; dry-run performs zero provider calls and zero writes; all vectors are generated and dimension-validated before the first write.
  - `scripts/backfill_embeddings.py`: CLI that refuses the in-memory fallback and never prints `MONGODB_URI`/API keys.
  - `tests/test_embedding_backfill.py` + `tests/mock_mongo.py`: 11 offline tests using a deterministic provider and mock MongoDB.
- **Acceptance Criteria**:
  - [x] Read-only audit reports existing embedding presence/dimensions (17 missing, 0 valid).
  - [x] Backfill targets only documents with missing/empty embeddings by default; `--mode invalid` / `--mode all` opt into broader rewrites.
  - [x] `$set`-style updates preserve `_id` and all metadata (covered by test).
  - [x] Dimension guard rejects mismatched vectors before any write (covered by test).
  - [x] Offline tests use mocked provider/Mongo; no real provider calls or live Atlas writes.
  - [x] Exact backfill command, required env vars, and verification steps documented below.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/test_embedding_backfill.py -v` → **11 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **94 passed**.
  - `scripts/backfill_embeddings.py --incident-id INC-2026-042 --dry-run` → `scanned: 17, missing: 17, valid: 0, eligible: 17, generated: 0, updated: 0`, no writes.
- **Backfill Command** (repo root, after operator approval):
  - Dry run: `backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042 --dry-run`
  - Live: `backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042`
- **Required Environment Variables** (in `.env` or `backend/.env`):
  - `MONGODB_URI=<atlas-connection-string>`
  - `MONGODB_DB_NAME=incident_investigator`
  - `EMBEDDING_PROVIDER=openai`
  - `EMBEDDING_API_KEY=<openai-key>`
  - `EMBEDDING_MODEL_NAME=text-embedding-3-small` (1536 dimensions)
- **Verification of Saved Embeddings**:
  - Rerun the dry run; expect `"missing": 0`, `"valid": 17`, `"eligible": 0`.
  - Or query Atlas read-only and assert 17 documents have a non-empty numeric `embedding` array of length 1536.
- **Blockers**: No vector search index exists in Atlas (`list_search_indexes()` returned `[]`). Backfill is not blocked, but `$vectorSearch` retrieval will fail after backfill until the `vector_index` defined in `backend/atlas_vector_index.json` is created.
- **Next Action**: With operator approval, run the live backfill command above, then create the `vector_index` Atlas Search index and re-run retrieval evaluation.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_embedding_backfill.py -v`

### Task BE-113: Migrate Embeddings & Answer Generation to Google Gemini
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-106, BE-108, BE-112
- **Scope**:
  - Default both providers to Gemini: `EMBEDDING_PROVIDER=gemini`, `LLM_PROVIDER=gemini`.
  - Replace deprecated `text-embedding-004` with a currently supported Gemini embedding model that can emit exactly 1536 dimensions to match `backend/atlas_vector_index.json`.
  - Use a free-tier-compatible Gemini generation model and correct `generateContent` request structure (`systemInstruction`, `contents`, `generationConfig`).
  - Preserve existing OpenAI embedding and generation support.
  - Add offline mocked tests for request payloads, response parsing, dimension enforcement, and configuration selection.
  - Update `.env.example` only; never write secrets to example files or the real `.env`.
- **Model Verification (Google Gemini API docs, 2026-10-31)**:
  - `gemini-embedding-2`: current stable multimodal embedding model; supports `outputDimensionality` 128–3072 (recommended 768/1536/3072) and auto-normalizes truncated dimensions. Free-tier text input is free of charge.
  - `gemini-embedding-001`: older stable model; supports 128–3072 but requires manual normalization below 3072. Kept as an accepted alternative.
  - `text-embedding-004` is not the current default and is no longer used by the shipped configuration.
  - `gemini-3.8-flash`: free-tier-compatible Gemini 3 generation model; Google recommends leaving temperature at the default 1.0 for Gemini 3.
- **Implementation**:
  - `backend/app/services/embeddings.py`: Gemini defaults to `gemini-embedding-2`, requests `outputDimensionality=1536`, validates returned dimension before storage, and rejects invalid/out-of-range dimensions. OpenAI `text-embedding-3-small` support is unchanged.
  - `backend/app/core/config.py`: Gemini defaults for both providers plus `EMBEDDING_DIMENSIONS=1536`.
  - `backend/app/services/generator.py`: Gemini defaults to `gemini-3.8-flash`, sends `systemInstruction` separately from the user `contents`, omits the Gemini 3 temperature override, skips thought parts, and reports safety blocks/empty candidates explicitly.
  - `.env.example` + `backend/.env.example`: Gemini variables and placeholders only. Removed a previously committed-looking API key value from `backend/.env.example`.
  - `tests/test_embeddings.py`: Gemini 1536-dim payload/dimension tests.
  - `tests/test_generator.py`: new offline Gemini request/response, safety, timeout, rate-limit, and OpenAI regression tests.
- **Acceptance Criteria**:
  - [x] Gemini embedding requests request and validate 1536 dimensions; mismatches fail before storage.
  - [x] Gemini generation uses the documented model endpoint, system instruction, and response shape.
  - [x] OpenAI configuration remains functional and covered by tests.
  - [x] Offline tests make no network calls and perform no Atlas writes.
  - [x] `.env.example` contains placeholders only and documents the exact Gemini variables.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py tests/test_embedding_backfill.py -v` → **58 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **110 passed**.
- **Environment / Backfill Commands**:
  - `.env` values: `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_API_KEY=<gemini-key>`, `EMBEDDING_MODEL_NAME=gemini-embedding-2`, `EMBEDDING_DIMENSIONS=1536`, `LLM_PROVIDER=gemini`, `LLM_API_KEY=<gemini-key>`, `LLM_MODEL_NAME=gemini-3.8-flash`.
  - Dry run: `backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042 --dry-run`
  - Live backfill (operator approval required): `backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042`
  - RAG test: `curl -s -X POST http://127.0.0.1:8000/api/incidents/INC-2026-042/query -H 'Content-Type: application/json' -d '{"query":"What caused the checkout latency and when did it start?","limit":5}'`
- **Blockers**: The `vector_index` Atlas Search index is still absent; live `$vectorSearch` retrieval will fail until it is created from `backend/atlas_vector_index.json`.
- **Next Action**: After operator approval, run the live backfill with Gemini, verify 17 valid 1536-dim vectors, create the `vector_index`, then exercise the RAG query endpoint.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py tests/test_embedding_backfill.py -v`

### Task BE-114: Verify Gemini `gemini-embedding-001` & Generation API Compatibility
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-113
- **Scope**:
  - Verify `gemini-embedding-001` uses the current documented batch embedding request format.
  - Confirm the request explicitly asks for 1536 dimensions and the response is validated at exactly 1536.
  - Confirm `gemini-3.8-flash` is a supported stable `generateContent` model and the payload matches the current schema.
  - Add offline mocked coverage for both embedding and generation providers; no live API calls.
- **API Verification (Google Gemini API docs, last updated 2026-10-26/28)**:
  - `models.batchEmbedContents` accepts `EmbedContentRequest` objects containing `model`, `content`, and `embedContentConfig`.
  - Top-level `outputDimensionality` is still accepted but marked deprecated; the current schema is `embedContentConfig.outputDimensionality`.
  - `gemini-embedding-001` supports 128–3072 output dimensions but does **not** auto-normalize truncated outputs; `gemini-embedding-2` does.
  - `gemini-3.8-flash` is listed as a stable Gemini 3 model, and `generateContent` accepts `systemInstruction`, `contents`, and optional `generationConfig`.
- **Implementation**:
  - `backend/app/services/embeddings.py`: Gemini batch requests now send `embedContentConfig: {"outputDimensionality": 1536}` instead of the deprecated top-level field. Responses are still validated as exactly 1536 dimensions. `gemini-embedding-001` vectors below its native 3072 dims are L2-normalized as required by Google's guidance.
  - `tests/test_embeddings.py`: added explicit `gemini-embedding-001` request payload, 1536-dim validation, non-1536 rejection, factory configuration, and normalization tests; updated the `gemini-embedding-2` payload assertion.
  - `tests/test_generator.py`: added explicit configured `gemini-3.8-flash` endpoint coverage and a `models/` prefix regression test.
  - `spec.md`: documented `embedContentConfig.outputDimensionality` and the `gemini-embedding-001` normalization requirement.
- **Acceptance Criteria**:
  - [x] `gemini-embedding-001` request uses `embedContentConfig.outputDimensionality`.
  - [x] 1536-dim request and exact response validation are covered by tests.
  - [x] Gemini generation model/payload compatibility is covered by tests.
  - [x] All tests run offline; full backend suite passes.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py -v` → **52 passed**.
  - `backend/.venv/bin/pytest tests/test_embeddings.py tests/test_generator.py tests/test_embedding_backfill.py -v` → **63 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **115 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app scripts tests` → clean.
- **Blockers / Unchanged Items**: No live API calls, Atlas backfill, commits, pushes, or branch switches were performed. `AGENTS.md` required no change because ownership/architecture did not change. The Atlas `vector_index` remains absent and real `backend/.env` still needs operator-supplied Gemini values (see BE-113).
- **Correction**: The field-placement claim above was disproven by a live backfill that returned 3072-dim vectors. See **BE-115**; `batchEmbedContents` ignores `embedContentConfig` and requires the per-item top-level `outputDimensionality`.

### Task BE-115: Fix Gemini `batchEmbedContents` Dimension Flag
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-114
- **Problem**: A live `gemini-embedding-001` backfill requested 1536 dims but received 3072-dim vectors, so validation rejected them before any writes. The payload nested the dimension under `embedContentConfig`, which the `batchEmbedContents` endpoint ignores.
- **Root Cause**:
  - `models.embedContent` accepts an `embedContentConfig` object.
  - `models.batchEmbedContents` takes `EmbedContentRequest` items whose dimension field is the per-item top-level `outputDimensionality`; the nested config object is not applied by that endpoint.
  - With no honored dimension flag, `gemini-embedding-001` returns its native 3072 dims.
- **Fix**:
  - `backend/app/services/embeddings.py`: every `requests[]` item now sends `outputDimensionality: 1536` at the top level; the ignored `embedContentConfig` object was removed.
  - Raw response vectors are validated at exactly 1536 dimensions by `_validate_vectors` **before** `_l2_normalize` runs, so a 3072 response still fails loudly instead of being truncated.
  - `gemini-embedding-001` L2 normalization for reduced (< 3072) dimensions is unchanged.
  - `tests/test_embeddings.py`: updated the exact batch payload assertions and added `test_gemini_batch_payload_uses_top_level_output_dimensionality` as a regression test; the existing 3072-rejection test remains.
  - `spec.md`: corrected the embedding contract to require the per-item top-level field for `batchEmbedContents`.
- **Acceptance Criteria**:
  - [x] Every `requests[]` item contains `outputDimensionality: 1536`.
  - [x] Raw response vectors are validated at exactly 1536 before normalization.
  - [x] `gemini-embedding-001` normalization is preserved.
  - [x] Mocked tests cover the payload and unexpected-dimension rejection; all tests run offline.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py -v` → **41 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **116 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app scripts tests` → clean.
- **Blockers / Unchanged Items**: No live backfill or API calls were made. The Atlas index remains 1536 dims. A live retry is tracked as BE-116 and needs operator approval plus the `vector_index`.

### Task BE-116: Live Re-validation of Gemini 1536-dim Backfill
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-115, operator approval, Atlas search index
- **Verification (read-only, no Gemini calls, no writes)**:
  - `incident_investigator.incident_events` contains **17** docs for `INC-2026-042`.
  - Every sampled doc has an `embedding` list of exactly **1536** dims.
  - The deployed search index is named **`vector-index`**, `status=READY`, `queryable=True`, `numDimensions=1536`, `similarity=cosine`, with filter fields `incident_id`, `source_type`, `timestamp`.
- **Note**: The live backfill is confirmed present. The index was created as `vector-index` (hyphen), not the canonical `vector_index`; that mismatch caused BE-117.
- **Remaining (operator-only)**: a live Gemini-backed `POST /query` call was not performed in this session (out of scope). The retrieval half was validated end-to-end with a stub embedding provider.

### Task BE-117: Fix Empty RAG Retrieval (Vector Index Name Mismatch)
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-107, OPS-002
- **Symptom**: `POST /api/incidents/INC-2026-042/query` returned the insufficient-evidence answer with empty `citations` and `retrieved_events`, even though Atlas was reachable, the 17 docs existed, all embeddings were 1536 dims, and a search index was `READY`.
- **Root Cause (verified read-only against Atlas)**:
  - The deployed Atlas index is named **`vector-index`** (hyphen): `list_search_indexes()` reported `name='vector-index'`, `status='READY'`, `queryable=True`, and the expected 1536-dim cosine definition.
  - `RetrievalService.DEFAULT_INDEX_NAME` was **`vector_index`** (underscore), so `$vectorSearch` targeted a non-existent index name.
  - Atlas **does not raise** for the unknown index name in this cluster; it returns **0 documents** silently. `search_events()` therefore returned `[]`, and `generate_answer()` short-circuited to the insufficient-evidence phrase.
  - Evidence: the exact pipeline with a stored 1536-dim doc vector returned `n=0` for `vector_index` and `n=5` for `vector-index`; `{"incident_id": "INC-2026-042"}` (no `$eq`) also returned 5, ruling out the filter.
- **Fix**:
  - `backend/app/core/config.py`: added `VECTOR_INDEX_NAME` (default canonical `vector_index`, `min_length=1`).
  - `backend/app/services/retrieval.py`: `RetrievalService` resolves `index_name` from settings; added `_assert_configured_index_available()` so an empty result set with a missing/non-queryable index raises `VectorIndexNotFoundError` instead of silently returning `[]`.
  - `backend/.env`: set `VECTOR_INDEX_NAME=vector-index` for the existing deployment (non-secret local config).
  - `.env.example`, `backend/.env.example`, `spec.md`, `README.md`, `backend/atlas_vector_index.json`: documented the configurable index name and Atlas's silent-empty behavior.
  - Added the previously missing `tests/test_retrieval.py` (pipeline/index/filters/mapping + silent-empty regression).
- **Acceptance Criteria**:
  - [x] `RetrievalService` uses the configured `VECTOR_INDEX_NAME`.
  - [x] Empty results with a missing index raise `VectorIndexNotFoundError` (no silent empty retrieval).
  - [x] The exact `$vectorSearch` pipeline is covered by mocked tests.
  - [x] All tests run offline; no live Gemini/Atlas writes.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/test_retrieval.py -v` → **12 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **128 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app scripts tests` → clean.
  - Read-only live check: `RetrievalService` (stub embeddings) against Atlas returned **5** events: `SLACK-308, ALERT-203, SLACK-309, SLACK-304, ALERT-205`.
  - Uvicorn dev server reloaded with `VECTOR_INDEX_NAME=vector-index`; `/api/health` → `{"status":"ok","database":"connected"}`.
- **Blockers / Unchanged Items**: No live Gemini calls, no Atlas writes, no index changes, no commits/pushes, no branch switch. A full live `POST /query` (which calls Gemini for the query embedding and answer) remains operator-run.

### Task BE-118: Diagnose Generic 503 from Live RAG Query
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-109, BE-117
- **Symptom**: `POST /api/incidents/INC-2026-042/query` returns `{"detail":"LLM provider unavailable or rate-limited"}` immediately after retrieval was verified.
- **Investigation (no live API calls)**:
  - The endpoint maps `GeneratorRateLimitError`, `GeneratorProviderError`, and `GeneratorConfigurationError` all to **HTTP 503** with the same generic detail.
  - `generate_answer()` previously replaced every provider exception message with `"LLM provider unavailable or rate-limited"` and even converted `GeneratorConfigurationError` into `GeneratorProviderError` via a broad `except Exception`, so the real HTTP status, Gemini `error.status`, and model name were lost before logging.
  - `GeminiLLMProvider` parsed only the HTTP status, not the response error body, and treated all non-429 4xx/5xx as the same category.
  - Config audit (non-secret): `LLM_PROVIDER=gemini`, `LLM_MODEL_NAME=gemini-3.8-flash`, key present, identical to the embedding key.
  - Docs audit (2026-10-28 models page): `gemini-3.8-flash` **is** a valid stable model (`gemini-3.8-flash`, released 2026-09-02, no shutdown). The request payload (`systemInstruction` + `contents[role=user]`) matches the documented `generateContent` schema, and the URL/`x-goog-api-key` header are correct.
  - Therefore the most likely live causes are credential/model-access (`401`/`403`), quota (`429`), or upstream failure — previously indistinguishable because the status and error category were hidden.
- **Implemented Fix** (`backend/app/services/generator.py`, `backend/app/api/incidents.py`):
  - `GeneratorProviderError` now carries non-secret diagnostics: `provider`, `model`, `status_code`, `provider_status`, `error_category`.
  - Added `_provider_error_details()`, `_raise_for_provider_error()`, `_classify_provider_error()`, `_sanitize_provider_message()`, and `describe_exception_for_logging()`.
  - `GeminiLLMProvider` and `OpenAILLMProvider` now parse provider error bodies (`error.status` / `error.type`), map statuses to stable categories (`authentication_failed`, `permission_denied`, `model_not_found`, `rate_limited`, `provider_unavailable`, ...), and attach `provider`/`model`/`category` to timeout and network failures.
  - Upstream messages are sanitized (Gemini/OpenAI-style keys and `key=`/`token=` values redacted, truncated to 300 chars) before storage/logging.
  - `generate_answer()` now preserves `GeneratorError` subclasses (no message replacement, no configuration-error misclassification) and wraps only truly unexpected exceptions.
  - The query endpoint logs a structured, sanitized diagnostic record (exception type, provider, model, status, provider status, category, sanitized message). The client-facing contract is unchanged: `503 "LLM provider unavailable or rate-limited"` and `504 "LLM provider timed out"`.
- **Verification**:
  - `backend/.venv/bin/pytest tests/test_generator.py tests/test_api_query.py -v` → **35 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **146 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app tests` → clean.
  - New mocked coverage: Gemini 400/401/403/404/429/500/503 mapping, OpenAI 401 mapping, timeout diagnostics, API-key/token redaction, exception preservation, endpoint 503/504 mapping, configuration-error classification, and log redaction.
- **Acceptance Criteria**:
  - [x] Provider exceptions expose `provider`, `model`, `status_code`, `error_category`.
  - [x] Logs distinguish auth/permission/model-not-found/rate-limit/5xx without leaking secrets.
  - [x] Client response stays a generic 503/504 (no upstream body or key leakage).
  - [x] Mocked tests cover 400/401/403/404/429/5xx and endpoint error mapping.
- **Open Item**: The exact live upstream status is still unverified because no live Gemini calls were permitted. Operator follow-up is tracked as **OPS-003**: run one query and read the new safe log fields.

### Task BE-119: Investigate Confirmed Live Gemini Generation Timeout (30s)
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-118, OPS-003
- **Confirmed Live Evidence**:
  - Gemini embedding request succeeds with HTTP 200.
  - Generation fails with `GeneratorTimeoutError`: `LLM request timed out after 30.0 seconds`.
  - Endpoint returns HTTP 504.
  - Provider/model: Gemini `gemini-3.8-flash`.
  - Atlas retrieval previously returned 5 events.
- **Confirmed by Offline Inspection**:
  - `DEFAULT_LLM_TIMEOUT = 30.0` and `httpx.Client(timeout=self.timeout)` apply 30 seconds **per HTTP phase** (connect, read, write, pool), not as one total wall-clock deadline.
  - In production the provider is created without a shared client, so each request creates and closes a new `httpx.Client`. A test-injected client bypasses `self.timeout`.
  - There are no retries in the generation path. `Generator.query()` performs one retrieval and exactly one `provider.generate()` call; covered by a new mocked test.
  - For the 5 verified retrieved IDs (`SLACK-308`, `ALERT-203`, `SLACK-309`, `SLACK-304`, `ALERT-205`), the generated prompt is small: system prompt 1,229 chars, context 2,022 chars, total payload 3,539 JSON bytes (~844 rough tokens). Context size is therefore not a plausible cause of a 30-second delay.
  - The query route is `async def` but calls the synchronous `Generator.query()` directly, so a slow generation blocks the event loop; this does not itself cause the httpx timeout but is a real concurrency defect.
  - No application log files are stored in the repo, so the exact timeout phase and server-side latency were not available before this task.
- **What Remains Unverified**:
  - Whether the timeout occurred during **connect** (DNS/TLS/egress/proxy) or **read** (connection established, response delayed).
  - Whether the cause is model latency, thinking-token defaults, region/proxy latency, or an upstream stall. The model must **not** be described as slow or unavailable without evidence.
  - Whether the frontend issued duplicate requests: the frontend directory is not present on this branch, so only backend call count was verified.
- **Implemented Diagnostic Change** (`backend/app/services/generator.py`):
  - Added `timeout_phase` to `GeneratorProviderError` and `describe_exception_for_logging()`.
  - Timeout messages now include the phase, e.g. `LLM request timed out after 30.0 seconds (phase=read)`.
  - Added `_timeout_phase()` mapping `httpx.ConnectTimeout`/`ReadTimeout`/`WriteTimeout`/`PoolTimeout` to `connect`/`read`/`write`/`pool`.
  - The 30-second default is unchanged, preserving the `spec.md` contract.
- **Mocked Verification**:
  - `backend/.venv/bin/pytest tests/test_generator.py tests/test_api_query.py -q` → **42 passed**.
  - `backend/.venv/bin/pytest tests/ -q` → **153 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app tests` → clean.
  - New tests cover every timeout phase, log-field exposure, the unchanged 30-second default, and exactly one LLM call per query.
- **Recommended Smallest Next Step**:
  1. Operator runs **one** live query (OPS-004) and reads `timeout_phase` in the 504 log line.
  2. If `read`: the connection succeeded and the response was slow. Then a targeted read-timeout increase (for example 60s) is the smallest plausible adjustment, with the trade-off that each request holds a worker and connection twice as long and may still be cut off by a client/proxy; changing the documented 30s default needs team agreement.
  3. If `connect`: investigate DNS/TLS/egress/proxy first; raising the timeout would likely mask a network problem.
  4. If `write` or `pool`: unexpected for a ~3.5 KB payload on a fresh client; investigate client reuse/connection pooling rather than the model.
- **Follow-ups Recorded**: **OPS-004** (capture timeout phase), **BE-120** (non-blocking async query execution), **BE-121** (configurable timeout / reusable client, blocked on OPS-004 evidence).
- **Constraints Honored**: No live Gemini calls, no Atlas writes, no backfill, no secret exposure, no commits/pushes, no branch switch.

### Task BE-122: Audit Read-Phase Gemini Generation Request Against Official Docs
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-119, OPS-004
- **Confirmed Production Diagnostic**:
  - `gemini-embedding-001:batchEmbedContents` succeeds with HTTP 200.
  - `gemini-3.8-flash` generation times out at 30s with `phase=read`.
  - The request reaches read phase but no HTTP status arrives before the timeout.
  - Prompt is ~3.5 KB; duplicate backend generation calls ruled out.
- **Docs Audit — Request Shape Matches Official REST Contract**:
  - URL built in `backend/app/services/generator.py` (`GeminiLLMProvider.generate`): `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, with `model_name = self.model.removeprefix("models/")`. This matches the documented endpoint `POST https://generativelanguage.googleapis.com/v1beta/{model=models/*}:generateContent`; the `models/` normalisation prevents a doubled prefix.
  - Headers: `x-goog-api-key: <key>` and `Content-Type: application/json`. Both are the documented REST auth/header pattern (the docs' `?key=` curl form is an alternative, not the only form).
  - Payload from `_build_gemini_payload`: `systemInstruction.parts[].text` plus `contents[{role: "user", parts: [{text}]}]`. Both are valid `GenerateContentRequest` fields.
  - Model name `gemini-3.8-flash` is a currently listed, generally available model and is free-tier eligible on the pricing page. No doc evidence that the identifier itself is invalid or preview-gated.
  - Conclusion: the request is well-formed. The timeout is **not** explained by a malformed URL, wrong header, wrong payload shape, or unknown model.
- **Docs Audit — Generation Settings (Latency-Relevant)**:
  - The payload includes **no `generationConfig` at all**, so every default applies.
  - Official thinking docs state `gemini-3.8-flash` defaults to **thinking On (medium)**, with `low`/`medium`/`high` supported, and that Gemini models adjust reasoning effort dynamically by default.
  - `GenerationConfig.thinkingConfig.thinkingLevel` exists in the `generateContent` schema and is currently **not set**, so the app inherits medium thinking.
  - `maxOutputTokens` is also unset, so the model may spend up to its output limit on thinking tokens; the docs state thinking tokens are billed/counted as output tokens.
  - Official guidance is to lower `thinkingLevel` to reduce cost/latency, and that a small `maxOutputTokens` can truncate reasoning instead.
  - `temperature`, `topP`, `topK`, `candidateCount`, `safetySettings`, tools and cached content are all unset — none of these are plausible causes of a 30s stall.
  - Net: default medium thinking is a **plausible latency contributor**, not a proven cause.
- **Docs Audit — Client Semantics (Strongest Structural Evidence)**:
  - `httpx.Client(timeout=30.0)` applies 30s **per phase**; `generateContent` is a non-streaming call, so no response bytes (not even a status line) are emitted until generation completes.
  - Therefore the 30s **read** timeout behaves as a total generation deadline for this call. Any generation that finishes after 30s produces exactly the observed signature: connection established, then silence, then `ReadTimeout` with no HTTP status.
  - `phase=read` (not `connect`) also confirms DNS/TLS/egress to `generativelanguage.googleapis.com` is working, corroborated by the same host returning HTTP 200 for embeddings.
  - Creating a fresh client per request adds only milliseconds and no retries occur; neither explains 30s.
- **Non-Billable Access Validation (confirmed from official billing docs)**:
  - Billing FAQ "What am I billed for?" lists only: input token count, output token count, cached token count, cached token storage duration. Metadata calls are not in that list.
  - Billing FAQ explicitly states: *"Is GetTokens billed? Requests to the GetTokens API are not billed, and they don't count against inference quota."* — so `models.countTokens` is confirmed non-billable.
  - Therefore `GET https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash` (`models.get`, empty request body, `x-goog-api-key` header) is a safe, minimal, non-billable access check. Its `Model` response exposes `supportedGenerationMethods` (should include `generateContent`) and `thinking`.
  - Limitation to record honestly: `models.get` proves model visibility/capability for the key/project. It does **not** prove quota headroom, latency, or that generation will succeed.
- **Hypotheses (ranked, with supporting evidence)**:
  1. **Generation exceeds 30s because of default thinking** — best fit for `phase=read` + no status: non-streaming response emits nothing until completion; default medium thinking plus no `maxOutputTokens`. Supported by docs; **unproven** because no generation duration has ever been measured.
  2. **Upstream stall / regional contention / free-tier queueing** — would also produce `phase=read`. Docs publish no latency SLO and no free-tier queueing behaviour. A quota breach would normally surface as HTTP 429, not a silent hang.
  3. **Proxy/middlebox holds or buffers the response** — possible; a small fast embedding on the same host argues against a general egress failure, but does not rule out response buffering on larger POSTs. No evidence either way.
  4. **Request rejected but response lost** — unlikely: argument/auth errors return 4xx quickly; a total absence of status argues against it.
  5. **Wrong model/endpoint** — ruled out by the docs audit above.
- **Single Smallest Next Diagnostic Action**:
  - Operator runs **OPS-005**: one non-billable `GET /v1beta/models/gemini-3.8-flash` with the existing key and reads the metadata only. Expect HTTP 200, `supportedGenerationMethods` containing `generateContent`, and `thinking: true`.
  - If it returns 404/403, the cause is model access, not latency, and no timeout change is warranted.
  - If it returns 200, model access is eliminated and the only remaining unknown is timing. The next *approved* test should be a single request outside the app with a 120s client timeout and `thinkingLevel` left at default, to measure real duration; if it completes in e.g. 33s, hypothesis 1 is confirmed and the correct fix is `thinkingLevel=low` and/or streaming, not a blanket timeout increase.
  - Structural note for later (not this task): `:streamGenerateContent` would turn the read timeout from a total-generation deadline into an inter-chunk timeout, which is the more robust design if thinking latency is confirmed.
- **No Code Changed**: The request is docs-conformant and no evidence justifies altering timeout, model, provider, payload, or API behaviour. No tests added for the same reason (existing 153-pass suite remains the baseline).
- **Follow-ups Recorded**: **OPS-005** (non-billable `models.get`), **BE-121** (configurable timeout/reusable client, still blocked on evidence), **BE-120** (non-blocking async query).
- **Constraints Honored**: No live Gemini calls, no Atlas writes, no backfill, no secret exposure, no commits/pushes, no branch switch.

### Task BE-123: Harden Gemini Generation Path (`thinkingLevel`, Bounded Retries, Deadline)
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-122, OPS-005
- **New Confirmed Evidence (live, operator-run)**:
  - `GET /v1beta/models/gemini-3.8-flash` → HTTP 200, so the model is visible to the key/project.
  - Two independent minimal `generateContent` requests (`thinkingLevel: low`, `maxOutputTokens: 64`) returned **HTTP 503 UNAVAILABLE in ~1.1–1.4 s**, with Google's "model experiencing high demand" message.
  - The application previously hit an httpx read timeout after 30 s.
  - The real RAG prompt is ~3.5 KB; embeddings and Atlas retrieval are already verified.
- **Classification**: The 503 is a **provider availability response**, not a confirmed application bug. Nothing in this task claims to fix Google's capacity issue; it makes the application degrade predictably and retry transient failures within a fixed budget.
- **Implemented**:
  - `LLM_GEMINI_THINKING_LEVEL` (default `low`) sent only to Gemini via `generationConfig.thinkingConfig.thinkingLevel`; `none`/`off`/`default` omits `thinkingConfig`; OpenAI payloads unchanged.
  - Shared bounded retry helper for Gemini and OpenAI: retryable statuses `429, 500, 502, 503, 504`; connect/pool timeouts only; exponential backoff with jitter (`0.5s` base, `4.0s` cap, `3` total attempts by default).
  - Permanent client errors (`400/401/403/404`) and read/write timeouts fail immediately (no duplicated generation).
  - Hard overall deadline (`LLM_REQUEST_DEADLINE_SECONDS`, default `30.0s`) shared by attempts and sleeps; per-attempt timeout clamped to the remaining budget.
  - Retry logs contain only provider, model, status/phase, attempt, and delay — no prompts, payloads, or API keys.
  - API contract unchanged: `504 "LLM provider timed out"`, `503 "LLM provider unavailable or rate-limited"`; no model/provider fallback.
- **Verification**:
  - `backend/.venv/bin/pytest tests/test_generator.py -q` → **45 passed**.
  - New mocked coverage: 503→success, repeated 503 exhausting budget, permanent 403 not retried, read timeout not retried, deadline clamp/stop, retry-policy bounds, thinking config Gemini-only, factory settings, invalid thinking level, log redaction.
  - `backend/.venv/bin/pytest tests/ -q` → **166 passed**.
  - `backend/.venv/bin/python -m compileall -q backend/app tests` → clean.
- **Docs Synced**: `spec.md` §5.3 and §8 config list; `backend/.env.example`; `.env.example`.
- **Remaining Blocker (not code)**: Google's live `generateContent` still returns `503 UNAVAILABLE` due to provider capacity. The app now retries briefly and fails predictably within the budget, but it cannot manufacture provider availability. A future live check is the only way to confirm recovery.
- **Constraints Honored**: No live Gemini calls, no Atlas writes, no backfill, no secret exposure, no commits/pushes, no branch switch, no model/provider fallback.

### Task BE-124: Evaluate Explicit OpenAI LLM Provider Switch (Gemini 503 Blocker)
- **Primary Owner**: Person 1
- **Status**: **DONE**
- **Dependencies**: BE-123
- **Why**: Gemini generation repeatedly fails with provider-side `503 UNAVAILABLE` (high demand) plus a 30s read timeout. Embeddings and Atlas retrieval are already working, so the goal is to restore reliable answer generation without touching the retrieval/embedding contract.
- **Decision**: **Configuration only; no code changes required.** The existing `OpenAILLMProvider` is complete and already routed by explicit configuration. Gemini remains the default and is preserved.
- **Inspection Findings (actual repository state)**:
  - `backend/app/services/generator.py` `OpenAILLMProvider` sends `POST https://api.openai.com/v1/chat/completions` with `Authorization: Bearer <LLM_API_KEY>`, `model`, `messages` (`system` + `user`), and `temperature: 0.1`; it parses `choices[0].message.content`.
  - It uses the same bounded retry/deadline helper as Gemini (`429, 500, 502, 503, 504`; connect/pool timeouts only; 30s default deadline) and maps `401/403/404/429/5xx` to safe diagnostics. No automatic provider fallback exists.
  - `create_llm_provider()` selects OpenAI only when `LLM_PROVIDER=openai`; it reads `LLM_API_KEY`, `LLM_MODEL_NAME`, and the shared retry/deadline settings. It defaults the model to `gpt-4o-mini`.
  - The app does **not** read `OPENAI_API_KEY`; the OpenAI key must be placed in `LLM_API_KEY`.
  - Embeddings are fully independent: `RetrievalService._get_query_embedding()` uses `get_embedding_provider()` driven by `EMBEDDING_PROVIDER` / `EMBEDDING_API_KEY`. Keeping Gemini embeddings leaves stored 1536-dim vectors, the `vector-index` name, and retrieval untouched.
  - Existing offline tests already cover OpenAI selection, request URL/payload, `401` mapping, and the guarantee that Gemini thinking fields are never sent to OpenAI.
- **Current Non-Secret Local Configuration** (from `backend/.env`):
  - `LLM_PROVIDER=gemini`, `LLM_MODEL_NAME=gemini-3.8-flash`
  - `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_MODEL_NAME=gemini-embedding-001`, `EMBEDDING_DIMENSIONS=1536`, `VECTOR_INDEX_NAME=vector-index`
  - `LLM_API_KEY` is currently the same Gemini key as `EMBEDDING_API_KEY`; no OpenAI key is present in the environment.
- **Exact Configuration-Only Switch** (edit `backend/.env` or the deployment environment, then restart the backend):
  - Change `LLM_PROVIDER=openai`
  - Change `LLM_API_KEY=<OpenAI API key>` (must replace the current Gemini key)
  - Change `LLM_MODEL_NAME=gpt-4o-mini` (or another OpenAI chat-completions model enabled on the account)
  - **Keep unchanged**: `EMBEDDING_PROVIDER=gemini`, `EMBEDDING_API_KEY=<current Gemini key>`, `EMBEDDING_MODEL_NAME=gemini-embedding-001`, `EMBEDDING_DIMENSIONS=1536`, `VECTOR_INDEX_NAME=vector-index`
  - `LLM_GEMINI_THINKING_LEVEL` is ignored by OpenAI and may stay as-is. `LLM_MAX_ATTEMPTS`, retry delays, and `LLM_REQUEST_DEADLINE_SECONDS` apply to OpenAI too.
  - Switching only `LLM_PROVIDER` while leaving the Gemini key/model in place will fail (`401`/`404`); all three LLM values must change together.
- **OpenAI Billing Requirement**: A ChatGPT Plus/Pro subscription does **not** include OpenAI API credits. The operator needs a separate OpenAI Platform API key with billing/credits enabled; API usage is billed independently.
- **Documentation Sync (no contract change)**: `.env.example` and `backend/.env.example` now warn that `LLM_API_KEY`/`LLM_MODEL_NAME` must match `LLM_PROVIDER` and that OpenAI keys/billing are separate. `spec.md` §8 documents explicit, non-fallback provider selection and the mixed OpenAI-generation + Gemini-embedding configuration.
- **Verification Results**:
  - `backend/.venv/bin/pytest tests/ -q` → **166 passed**, 1 pre-existing Starlette/httpx deprecation warning.
  - `backend/.venv/bin/python -m compileall -q backend/app scripts tests` → clean.
  - Factory probe with an OpenAI config returned `OpenAILLMProvider`, model `gpt-4o-mini`, base URL `https://api.openai.com/v1`, timeout `30.0`, and the configured retry policy.
- **Constraints Honored**: No live API calls, no spend, no Atlas writes, no embedding/index/retrieval changes, no secret exposure, no commits/pushes, no branch switch, no runtime fallback.
- **Next Single Action**: Add a funded OpenAI API key to `backend/.env` as `LLM_API_KEY`, set `LLM_PROVIDER=openai` and `LLM_MODEL_NAME=gpt-4o-mini`, restart the backend, and run one live `POST /api/incidents/INC-2026-042/query`.
- **Remaining Blockers**: No OpenAI API key/billing is configured locally, so the switch is not live-verified yet. Gemini's `503 UNAVAILABLE` remains a provider-side capacity issue and is bypassed, not fixed.

---

## 5. Person 2 — Frontend and Integration

### Task FE-201: Frontend Scaffolding, TanStack Router & Tailwind CSS
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: None
- **Scope**:
  - React 19 + TypeScript + Vite single-page app setup in `frontend/`.
  - TanStack Start / TanStack Router configured with file-based routing.
  - Tailwind CSS configured for dark/light theme styling with Radix UI primitives.
- **Acceptance Criteria**:
  - [x] Application structure initialized with complete routing tree.
  - [x] Route matching verified by unit tests in `frontend/src/test/app-routing.test.tsx`.
- **Verification Reference**:
  - `origin/frontend:frontend/src/router.tsx` and `origin/frontend:frontend/src/test/app-routing.test.tsx`.

### Task FE-202: Shared Types & Offline Mock API Layer (`mockApi.ts`)
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: FE-201, DATA-301
- **Scope**:
  - Define TypeScript interfaces in `frontend/src/types/api.ts` strictly matching `spec.md`.
  - Build offline fixture adapter `frontend/src/mocks/mockApi.ts` loading `frontend/src/mocks/inc_2026_042.json`.
  - Implement mock query handler supporting the 5 golden preset prompts, citation extraction, unverified citation simulation, and negative query handling.
- **Acceptance Criteria**:
  - [x] Mock API simulates network latency and returns strictly typed responses.
  - [x] Tested with unit tests in `frontend/src/test/mockApi.test.ts` (6 test cases).
- **Verification Reference**:
  - `origin/frontend:frontend/src/test/mockApi.test.ts`.

### Task FE-203: Deterministic Timeline UI with Time/Type Filters
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: FE-202
- **Scope**:
  - Build `TimelineView.tsx` component.
  - Render events sorted chronologically with source type badges (`slack`, `monitoring_alert`, `deployment_log`).
  - Add start/end UTC datetime inputs and source-type filter checkboxes.
  - Implement skeleton loading states, error toasts, and event click selection.
- **Acceptance Criteria**:
  - [x] Timeline updates dynamically on filter change.
  - [x] Visual highlight on selected/cited event.
- **Verification Reference**:
  - `origin/frontend:frontend/src/components/TimelineView.tsx`.

### Task FE-204: Investigation Chat with Grounded Citations & Quick Prompts
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: FE-202
- **Scope**:
  - Build `ChatInterface.tsx` and `CitationChip.tsx`.
  - Provide 5 quick prompt presets matching evaluation questions.
  - Parse citation tags `\[([A-Z]+-\d+)\]` and replace with interactive `<CitationChip>` components.
  - Highlight unverified citations with warning icon and explanatory tooltip.
  - Display distinctive callout for insufficient-evidence responses.
- **Acceptance Criteria**:
  - [x] Citations rendered as clickable chips that trigger event inspection.
  - [x] Unverified citations visually distinguished.
- **Verification Reference**:
  - `origin/frontend:frontend/src/components/ChatInterface.tsx` and `CitationChip.tsx`.

### Task FE-205: Event Detail Slide-Over Drawer
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: FE-202
- **Scope**:
  - Build `EventDrawer.tsx` utilizing Radix UI Sheet.
  - Display full raw content, structured payload JSON, author, channel/service, timestamp, and tags.
- **Acceptance Criteria**:
  - [x] Opens smoothly upon clicking any timeline event row or citation chip.
- **Verification Reference**:
  - `origin/frontend:frontend/src/components/EventDrawer.tsx`.

### Task FE-206: Dashboard & Incident JSON Import Views
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: FE-202
- **Scope**:
  - Build `DashboardView.tsx` with active incident summary cards.
  - Build `routes/import.tsx` for pasting or uploading raw incident JSON datasets.
- **Acceptance Criteria**:
  - [x] Successfully imports JSON into active session state.
- **Verification Reference**:
  - `origin/frontend:frontend/src/components/DashboardView.tsx` and `routes/import.tsx`.

### Task FE-207: Frontend Test Suite Execution & Component Tests
- **Primary Owner**: Person 2
- **Status**: **IN PROGRESS (on `frontend` branch)** (Next for Person 2)
- **Dependencies**: FE-203, FE-204
- **Scope**:
  - Run Vitest test suite (`npm test`) on the frontend branch once dependencies are installed.
  - Add component tests for `CitationChip` interaction, `TimelineView` filtering, and `EventDrawer` opening.
- **Acceptance Criteria**:
  - [ ] Vitest runs cleanly with 0 failures on all frontend unit and component tests.
  - [ ] `npm run build` generates production bundle without TypeScript errors.
- **Verification Command**:
  - `cd frontend && npm test && npm run build`

### Task FE-208: Live Backend API Integration (`VITE_USE_MOCK=false`)
- **Primary Owner**: Person 2
- **Status**: **BLOCKED**
- **Dependencies**: BE-109, Branch Merge
- **Blocker Reason**: Backend investigation query endpoint (`POST /api/incidents/{incident_id}/query`) is not yet implemented on `backend-dev`, and frontend code lives on a separate branch `frontend`. Also, Person 2's `/investigations` persistence requires backend contract decision.
- **Next Action**: Person 1 completes `BE-109`. Coordinate merging `origin/frontend` into integration branch.

---

## 6. Person 3 — Data and Evaluation

### Task DATA-301: Synthetic Golden Incident Dataset (`INC-2026-042`)
- **Primary Owner**: Person 3
- **Status**: **DONE**
- **Dependencies**: None
- **Scope**:
  - Curate comprehensive incident dataset in `data/incidents/inc_2026_042.json`.
  - 17 verified events covering normal state, deployment, alerts, triage chat, disk-full red herring, root cause discovery, rollback, recovery alert, and unproven Stripe hypothesis.
- **Acceptance Criteria**:
  - [x] All 17 events have valid ISO-8601 UTC timestamps, unique `source_id`s, and structured payloads.
  - [x] Verified by ingestion parser in `tests/test_ingestion.py`.
- **Verification Reference**:
  - `data/incidents/inc_2026_042.json` (17 records).

### Task DATA-302: Evaluation Benchmark Definition (`data/eval_cases.json`)
- **Primary Owner**: Person 3
- **Status**: **DONE**
- **Dependencies**: DATA-301
- **Scope**:
  - Author golden benchmark queries in `data/eval_cases.json` covering:
    1. First sign of trouble (`ALERT-201`)
    2. Responders and commander (`SLACK-301`, `SLACK-302`, `SLACK-303`)
    3. Preceding deployment (`DEPLOY-101`)
    4. Recovery evidence (`ALERT-205`, `SLACK-307`)
    5. Root cause vs unproven facts (`SLACK-305`, `SLACK-309`)
    6. Negative test / insufficient evidence (`EVAL-006`)
- **Acceptance Criteria**:
  - [x] Each case defines `expected_source_ids`, `minimum_expected_source_ids`, `acceptable_supplementary_ids`, `unacceptable_hallucinated_ids`, and ground truth summary.
- **Verification Reference**:
  - `data/eval_cases.json` (6 test cases).

### Task DATA-303: Automated Retrieval Evaluation Harness
- **Primary Owner**: Person 3
- **Status**: **PENDING** (Next for Person 3)
- **Dependencies**: DATA-302, BE-107
- **Scope**:
  - Implement `tests/test_retrieval_eval.py` and evaluation runner script `scripts/run_eval.py`.
  - Execute queries against `$vectorSearch` and check retrieved candidate IDs against expected IDs.
  - Coordinate interface with Person 1's `RetrievalService` without modifying backend pipeline logic.
- **Acceptance Criteria**:
  - [ ] Automated script runs all 6 evaluation cases and outputs structured results.
  - [ ] Retrieval benchmark passes in CI.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_retrieval_eval.py -v`

### Task DATA-304: Benchmark Metrics Reporting (Hit Rate@K, MRR, Latency)
- **Primary Owner**: Person 3
- **Status**: **PENDING**
- **Dependencies**: DATA-303
- **Scope**:
  - Compute standard information retrieval metrics:
    - **Hit Rate@5**: Proportion of queries where at least one ground-truth ID is in top 5.
    - **Mean Reciprocal Rank (MRR)**: Average reciprocal rank of the first relevant document.
    - **Retrieval Latency**: P50, P95, and P99 query latency in milliseconds.
- **Acceptance Criteria**:
  - [ ] Target: Hit Rate@5 = 100%, MRR >= 0.85, P95 retrieval latency < 500ms.
  - [ ] Formatted benchmark markdown summary artifact generated.
- **Verification Command**:
  - `python scripts/run_eval.py --report`

### Task DATA-305: Contradictory & Insufficient Evidence Scenarios
- **Primary Owner**: Person 3
- **Status**: **PENDING**
- **Dependencies**: DATA-302
- **Scope**:
  - Create targeted incident records exhibiting direct contradictions (e.g., metric alert says CPU 98% vs chat message says CPU normal).
  - Add test queries evaluating whether the RAG pipeline flags contradictions rather than picking one arbitrarily.
- **Acceptance Criteria**:
  - [ ] LLM output explicitly highlights the discrepancy between contradictory records.
  - [ ] Negative queries consistently trigger the standard insufficient evidence statement without hallucinations.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_eval_contradictions.py -v`

### Task DATA-306: Generation Grounding & Citation Correctness Benchmark
- **Primary Owner**: Person 3
- **Status**: **PENDING**
- **Dependencies**: BE-108, DATA-303
- **Scope**:
  - Evaluate citation precision and recall across full query generation responses.
  - Assert that 0% of unacceptable hallucinated IDs (`unacceptable_hallucinated_ids` in `eval_cases.json`) appear in verified citations.
- **Acceptance Criteria**:
  - [ ] Citation precision = 100% (zero hallucinated citations survive post-processor).
  - [ ] Citation recall >= 90% across golden queries.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_citation_eval.py -v`

---

## 7. Operational Verification

### Task OPS-001: Verify Live MongoDB Atlas Database/Collection/Persistence
- **Primary Owner**: Shared (Person 1, backend audit)
- **Status**: **DONE**
- **Dependencies**: BE-103, BE-105
- **Scope**:
  - Confirm the effective `MONGODB_DB_NAME` and whether `MONGODB_URI` is configured (never print the URI/credentials).
  - Check read-only whether the configured database, `incident_events` collection, and documents exist on the connected Atlas cluster.
  - Confirm whether the app uses Atlas or the in-memory fallback.
  - Confirm the existing ingestion endpoint can create the collection and persist an event (without paid embedding/LLM calls).
- **Findings** (read-only audit, no writes, no secrets printed):
  - `MONGODB_URI` is configured, uses `mongodb+srv`, targets an Atlas host, and contains no placeholder token.
  - Effective `MONGODB_DB_NAME` = `incident_investigator`.
  - Atlas ping succeeds via both raw PyMongo and `app.core.db.get_database()`; `get_database()` returns a live database and `StorageService.is_in_memory` is `False`. **The app uses Atlas, not the fallback.**
  - Visible cluster databases: `admin`, `local`, `sample_mflix`. `incident_investigator` does **not** exist yet (empty DBs are not materialized), so `incident_events` does not exist and contains 0 documents.
  - No `incident_events` collection exists in any other visible database.
  - Authenticated credential has `atlasAdmin` on `admin`, so it can create the missing database/collection and write documents.
  - Code path confirmed: `POST /api/incidents/ingest` -> `StorageService.insert_events()` -> `ReplaceOne(..., upsert=True)` on `incident_events`; first write auto-creates the collection. `get_storage_service()` also calls `create_indexes()`, and `main.py` lifespan seeds `data/incidents/inc_2026_042.json` when the incident is absent.
  - Offline verification: `backend/.venv/bin/pytest tests/test_api_mongo.py tests/test_api.py tests/test_ingestion.py -q` => **25 passed** (mock Mongo + in-memory, no cloud writes).
- **Acceptance Criteria**:
  - [x] Findings recorded in `backlog.md` with exact next action.
  - [x] No secrets printed, no cloud resources created, no paid API calls made.
- **Verification Command**:
  - Read-only PyMongo audit against the configured cluster (list databases/collections/counts/indexes only).
- **Next Action**:
  - **OPS-002** (requires explicit approval because it creates cloud resources): start the backend with the existing `.env` (auto-seeds 17 events), or send the existing ingest request:
    ```bash
    cd /home/asus/MongoHack
    curl -sS -X POST http://127.0.0.1:8000/api/incidents/ingest \
      -H 'Content-Type: application/json' \
      --data @data/incidents/inc_2026_042.json
    ```
    Then verify with read-only checks that `incident_investigator.incident_events` contains 17 documents for `INC-2026-042`.

### Task OPS-002: Populate Atlas `incident_investigator.incident_events`
- **Primary Owner**: Person 1
- **Status**: **PENDING (needs approval)**
- **Dependencies**: OPS-001
- **Scope**:
  - Run the existing ingestion path against Atlas to create the database/collection and persist the demo dataset.
  - Do **not** call paid embedding/LLM APIs; the standard ingest path currently stores events without embeddings.
- **Acceptance Criteria**:
  - [ ] `incident_investigator.incident_events` exists with 17 documents for `INC-2026-042`.
  - [ ] `GET /api/incidents` and `GET /api/incidents/INC-2026-042/timeline` return the persisted data.
- **Verification Command**:
  - Read-only count: `db.incident_events.count_documents({"incident_id": "INC-2026-042"})` => 17.

---

## 8. Immediate Next Tasks by Role

- **Person 1 (Backend & RAG)**:
  - **Task BE-106B**: Add embedding retry/backoff and HTTP 503/504 mapping; then **BE-106C** to attach embeddings during ingestion before starting **BE-107**.
- **Person 2 (Frontend & Integration)**:
  - **Task FE-207**: Run and expand Vitest suite on `frontend` branch; verify full build `npm run build`.
- **Person 3 (Data & Evaluation)**:
  - **Task DATA-303**: Create evaluation test harness in `tests/test_retrieval_eval.py` and coordinate search interface with Person 1.
