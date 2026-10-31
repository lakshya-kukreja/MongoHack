# Project Backlog & Implementation Milestones

## 1. Executive Status Dashboard

| Task ID | Task Name | Owner | Status | Dependencies | Verification Command |
|---|---|---|---|---|---|
| **CORE-001** | Architecture, 3-Person Ownership & Spec Synchronization | Shared (P1/P2/P3) | **DONE** | None | Inspection of `AGENTS.md`, `spec.md`, `backlog.md` |
| **BE-101** | Backend Scaffolding, Virtualenv, Settings & Health API | Person 1 | **DONE** | None | `backend/.venv/bin/pytest tests/test_health.py -v` (4 passed) |
| **BE-102** | Canonical Event Schema & Heterogeneous Ingestion Engine | Person 1 | **DONE** | BE-101 | `backend/.venv/bin/pytest tests/test_ingestion.py -v` (11 passed) |
| **BE-103** | MongoDB Atlas Storage Layer & Index Management | Person 1 | **DONE** | BE-102 | `backend/.venv/bin/pytest tests/test_storage*.py -v` (9 passed) |
| **BE-104** | Deterministic Timeline Engine (Sorting & Windowing) | Person 1 | **DONE** | BE-103 | `backend/.venv/bin/pytest tests/test_timeline.py -v` (9 passed) |
| **BE-105** | Core REST API Endpoints (Ingest, Timeline, Events, List) | Person 1 | **DONE** | BE-103, BE-104 | `backend/.venv/bin/pytest tests/test_api*.py -v` (14 passed) |
| **BE-106** | Vector Embedding Generation Service (`embeddings.py`) | Person 1 | **PENDING** | BE-102 | Unit tests with mock embeddings |
| **BE-107** | MongoDB Atlas `$vectorSearch` Retrieval Service (`retrieval.py`) | Person 1 | **PENDING** | BE-103, BE-106 | `backend/.venv/bin/pytest tests/test_retrieval.py -v` |
| **BE-108** | Grounded LLM Generation & Citation Validation (`generator.py`) | Person 1 | **PENDING** | BE-107 | `backend/.venv/bin/pytest tests/test_generator.py -v` |
| **BE-109** | Investigation Query Endpoint (`POST /api/incidents/{id}/query`) | Person 1 | **PENDING** | BE-105, BE-108 | Integration tests for query & citations |
| **BE-110** | End-to-End Backend Verification & Error Hardening | Person 1 | **PENDING** | BE-109 | `backend/.venv/bin/pytest tests/ -v` (all suites) |
| **FE-201** | Frontend Scaffolding, TanStack Router & Tailwind CSS | Person 2 | **DONE (branch)** | None | Inspect `origin/frontend:frontend/package.json` |
| **FE-202** | Shared Types & Offline Mock API Layer (`mockApi.ts`) | Person 2 | **DONE (branch)** | FE-201, DATA-301 | Inspect `origin/frontend:frontend/src/mocks/` |
| **FE-203** | Deterministic Timeline UI with Time/Type Filters | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/TimelineView.tsx` |
| **FE-204** | Investigation Chat with Grounded Citations & Quick Prompts | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/ChatInterface.tsx` |
| **FE-205** | Event Detail Slide-Over Drawer (`EventDrawer.tsx`) | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/components/EventDrawer.tsx` |
| **FE-206** | Dashboard & Incident JSON Import Views | Person 2 | **DONE (branch)** | FE-202 | Inspect `origin/frontend:frontend/src/routes/` |
| **FE-207** | Frontend Test Suite Execution & Component Tests | Person 2 | **IN PROGRESS** | FE-203, FE-204 | `npm test` on frontend branch |
| **FE-208** | Live Backend API Integration (`VITE_USE_MOCK=false`) | Person 2 | **BLOCKED** | BE-109, Branch Merge | Verify query and timeline against live port 8000 |
| **DATA-301** | Synthetic Golden Incident Dataset (`INC-2026-042`) | Person 3 | **DONE** | None | `data/incidents/inc_2026_042.json` (17 events verified) |
| **DATA-302** | Evaluation Benchmark Definition (`data/eval_cases.json`) | Person 3 | **DONE** | DATA-301 | `data/eval_cases.json` (6 golden queries verified) |
| **DATA-303** | Automated Retrieval Evaluation Harness | Person 3 | **PENDING** | DATA-302, BE-107 | `backend/.venv/bin/pytest tests/test_retrieval_eval.py -v` |
| **DATA-304** | Benchmark Metrics Reporting (Hit Rate@K, MRR, Latency) | Person 3 | **PENDING** | DATA-303 | `python scripts/run_eval.py` output table |
| **DATA-305** | Contradictory & Insufficient Evidence Scenarios | Person 3 | **PENDING** | DATA-302 | Negative & contradictory test cases in eval suite |
| **DATA-306** | Generation Grounding & Citation Correctness Benchmark | Person 3 | **PENDING** | BE-108, DATA-303 | Citation validation score > 95% |

---

## 2. Shared Milestones (All Roles)

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

## 3. Person 1 — Backend and RAG

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
- **Status**: **PENDING** (Next for Person 1)
- **Dependencies**: BE-102
- **Scope**:
  - Create `backend/app/services/embeddings.py`.
  - Integrate with OpenAI (`text-embedding-3-small`, 1536 dims) or Gemini (`text-embedding-004`, 768 dims) using direct SDK / HTTP calls.
  - Implement batch embedding generation with retries, exponential backoff, and test mock.
- **Acceptance Criteria**:
  - [ ] `generate_embedding(text: str) -> list[float]` returns valid float vector.
  - [ ] `generate_embeddings_batch(texts: list[str]) -> list[list[float]]` handles batches up to 64 items.
  - [ ] Deterministic mock provider enabled during test runs.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_embeddings.py -v`

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

### Task BE-108: Grounded LLM Generation & Citation Validation (`generator.py`)
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-107
- **Scope**:
  - Create `backend/app/services/generator.py`.
  - Construct prompt with system instructions enforcing strict evidence grounding, `[SOURCE_ID]` citation tokens, and uncertainty handling.
  - Format context with explicit `[EVIDENCE RECORD <source_id>]` blocks sorted chronologically.
  - Implement post-processing citation validator: regex extraction of `\[([A-Z]+-\d+)\]`, cross-validation against retrieved IDs, stripping hallucinated IDs into `unverified_citations`.
  - Build structured `CitationRecord` list.
- **Acceptance Criteria**:
  - [ ] Answer correctly cites retrieved sources.
  - [ ] Hallucinated IDs (e.g. `SLACK-999`) stripped and flagged.
  - [ ] Returns exact fallback phrase when evidence is insufficient: `"Based on the retrieved incident records, there is insufficient evidence to answer this question."`.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_generator.py -v`

### Task BE-109: Investigation Query Endpoint
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-105, BE-108
- **Scope**:
  - Implement `POST /api/incidents/{incident_id}/query` in `backend/app/api/incidents.py`.
  - Accept `QueryRequest` (`query`, `limit`, `start_time`, `end_time`).
  - Wire embedding -> retrieval -> context assembly -> generation -> citation validation -> `QueryResponse`.
- **Acceptance Criteria**:
  - [ ] Returns `QueryResponse` matching `spec.md` with `answer`, `citations`, `unverified_citations`, `retrieved_events`.
  - [ ] Responds with HTTP 404 if incident does not exist.
  - [ ] Responds with HTTP 422 for malformed requests.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/test_api_query.py -v`

### Task BE-110: End-to-End Backend Verification & Hardening
- **Primary Owner**: Person 1
- **Status**: **PENDING**
- **Dependencies**: BE-109
- **Scope**:
  - Run full test suite with all unit, integration, and RAG tests.
  - Verify zero regressions across all 47 existing tests plus new query tests.
- **Acceptance Criteria**:
  - [ ] 100% of backend tests pass (`pytest tests/ -v`).
  - [ ] No hardcoded secrets or environment variables committed.
- **Verification Command**:
  - `backend/.venv/bin/pytest tests/ -v`

---

## 4. Person 2 — Frontend and Integration

### Task FE-201: Frontend Scaffolding, TanStack Router & Tailwind CSS
- **Primary Owner**: Person 2
- **Status**: **DONE (on `frontend` branch)**
- **Dependencies**: None
- **Scope**:
  - React 19 + TypeScript + Vite single-page app setup in `frontend/`.
  - TanStack Start / TanStack Router configured with file-based routing (`routes/__root.tsx`, `routes/index.tsx`, `routes/dashboard.tsx`, `routes/investigate/$incidentId.tsx`, `routes/import.tsx`).
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
- **Status**: **IN PROGRESS** (Next for Person 2)
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

## 5. Person 3 — Data and Evaluation

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

## 6. Immediate Next Tasks by Role

- **Person 1 (Backend & RAG)**:
  - **Task BE-106**: Implement `backend/app/services/embeddings.py` supporting batch generation, rate limiting, and test mock.
- **Person 2 (Frontend & Integration)**:
  - **Task FE-207**: Run and expand Vitest suite on `frontend` branch; verify full build `npm run build`.
- **Person 3 (Data & Evaluation)**:
  - **Task DATA-303**: Create evaluation test harness in `tests/test_retrieval_eval.py` and coordinate search interface with Person 1.
