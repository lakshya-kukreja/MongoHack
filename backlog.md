# Project Backlog & Implementation Milestones

## Overview
This backlog breaks down the **Incident Timeline Investigator** into 8 incremental, educational milestones. Each milestone includes:
1. **Core Objective & Scope**
2. **Prerequisite Concepts** (What the team must understand before writing code)
3. **Acceptance Criteria** (Measurable signals of completion)
4. **Estimated Complexity** (S / M / L)

---

## Milestone 0: Environment & Project Scaffolding
- **Scope**: Initialize backend directory, Python virtual environment, dependencies (`fastapi`, `uvicorn`, `pymongo`, `pydantic`, `pydantic-settings`, `pytest`, `httpx`), `.env.example`, `.gitignore`, and Git repository.
- **Concepts to Understand**:
  - *Virtual Environments*: Why we isolate Python packages per project to avoid system conflicts.
  - *FastAPI & ASGI*: How modern asynchronous Python web frameworks operate using `uvicorn`.
  - *Environment Configuration*: Why 12-factor apps keep credentials in environment variables and never in source code.
- **Acceptance Criteria**:
  - [ ] Git repository initialized with a comprehensive `.gitignore` (ignoring `.env`, `__pycache__`, `.venv/`, `node_modules/`, `dist/`).
  - [ ] `backend/requirements.txt` configured and successfully installed in `.venv`.
  - [ ] Minimal FastAPI app running at `http://localhost:8000/api/health` returning `{"status": "ok"}`.
  - [ ] Running `pytest` discovers the test suite and passes.

---

## Milestone 1: Event Schema, Ingestion Pipeline & Demo Dataset
- **Scope**: Define the Pydantic data models for incident events, create the JSON/JSONL parser for heterogeneous sources (Slack, alerts, deployments), and write the realistic demo dataset (`data/incidents/inc_2026_042.json`).
- **Concepts to Understand**:
  - *Heterogeneous Incident Data*: Why alerts, chat messages, and CI/CD logs look completely different in structure and how to map them to a canonical schema.
  - *Pydantic v2 Models*: How data parsing, type validation, and serialization work in Python.
  - *ISO-8601 Timestamps & UTC*: Why handling timestamps in UTC (`Z` offset) is crucial to avoid timezone calculation bugs.
- **Acceptance Criteria**:
  - [ ] Canonical `EventRecord` schema implemented in `backend/app/models/event.py`.
  - [ ] Ingestion module (`backend/app/services/ingestion.py`) handles:
    - Raw Slack messages (speaker, message text, channel, timestamp).
    - Monitoring alerts (metric breaches, thresholds, severity, service).
    - Deployment logs (commit hash, deployer, environment, status).
  - [ ] Synthetic incident dataset (`INC-2026-042`) created with 18 realistic, chronologically distributed records spanning normal state, deploy, latency alert, triage chat, red herring, root cause discovery, rollback, recovery alert, and unproven hypothesis.
  - [ ] Unit tests in `tests/test_ingestion.py` verify that valid records parse correctly and malformed timestamps/IDs raise validation errors.

---

## Milestone 2: MongoDB Atlas Storage & Vector Indexing
- **Scope**: Connect to MongoDB Atlas, create collection `incident_events`, manage indexes (compound index on `incident_id` + `timestamp`), and define the Atlas Vector Search index configuration.
- **Concepts to Understand**:
  - *MongoDB Documents vs Tables*: How flexible JSON-like documents accommodate structured payloads alongside unstructured text.
  - *Vector Embeddings*: How text is transformed into dense numerical vectors (arrays of floating point numbers) where semantic similarity corresponds to geometric proximity (cosine distance).
  - *Atlas `$vectorSearch`*: How MongoDB Atlas indexes vector embeddings alongside metadata filters to allow hybrid retrieval without maintaining a separate vector database.
- **Acceptance Criteria**:
  - [ ] Database client utility (`backend/app/core/db.py`) connects to MongoDB Atlas using `MONGODB_URI`.
  - [ ] Storage service (`backend/app/services/storage.py`) supports `insert_events()`, `get_event_by_id()`, `list_incidents()`, and health ping.
  - [ ] Script or documentation provides the exact Atlas Vector Search index JSON definition.
  - [ ] Unit/mock tests verify database storage and retrieval without requiring a live cloud cluster during CI.

---

## Milestone 3: Deterministic Timeline Engine & API
- **Scope**: Implement the deterministic timeline reconstruction engine that sorts, filters, and groups incident events chronologically. Expose the `/api/incidents/{incident_id}/timeline` endpoint.
- **Concepts to Understand**:
  - *Deterministic vs Non-Deterministic Operations*: Why event chronology must be calculated by sorting timestamps mathematically rather than asking an LLM to guess what happened first.
  - *Time Windowing & Filtering*: How investigators zoom in on specific 15-minute or 1-hour intervals to isolate incident cascades.
- **Acceptance Criteria**:
  - [ ] `TimelineService` in `backend/app/services/timeline.py` sorts events strictly by timestamp ascending.
  - [ ] Supports filtering by `start_time`, `end_time`, and `source_type` (e.g. only show alerts and deploys).
  - [ ] Endpoint `GET /api/incidents/{incident_id}/timeline` returns formatted chronological events.
  - [ ] Unit test in `tests/test_timeline.py` asserts that even if events are inserted out-of-order, the returned timeline is 100% sorted chronologically.

---

## Milestone 4: Semantic Vector Retrieval & Evaluation Cases
- **Scope**: Implement embedding generation and vector search retrieval via MongoDB Atlas `$vectorSearch` with metadata pre-filtering by `incident_id`. Build the automated retrieval evaluation test suite.
- **Concepts to Understand**:
  - *Embedding Models*: How queries like *"Who acknowledged the alert?"* are embedded into the same semantic space as Slack messages like *"Alice: Taking a look at the checkout errors now"*.
  - *Pre-filtering in Vector Search*: Why filtering by `incident_id` *before* vector ranking prevents retrieving events from unrelated incidents.
  - *Retrieval Evaluation Metrics*: Hit Rate@K, Mean Reciprocal Rank (MRR), and Precision@K.
- **Acceptance Criteria**:
  - [ ] Embedding service (`backend/app/services/embeddings.py`) integrates with embedding API with fallback or mock for testing.
  - [ ] Retrieval service (`backend/app/services/retrieval.py`) runs `$vectorSearch` filtered by `incident_id`.
  - [ ] Retrieval evaluation suite (`tests/test_retrieval_eval.py`) tests the 6 golden benchmark queries and asserts that the ground-truth `source_id`s appear in the top-5 retrieved results:
    1. First sign of trouble (`ALERT-201`)
    2. Who noticed and responded (`SLACK-301`, `SLACK-302`, `SLACK-303`)
    3. Preceding deployment (`DEPLOY-101`)
    4. Recovery evidence (`ALERT-204`, `SLACK-306`)
    5. Root cause vs unproven facts (`DEPLOY-101`, `SLACK-305`, `SLACK-307`)
    6. Missing evidence handling (negative test)

---

## Milestone 5: Grounded LLM Generation & Citation Validation
- **Scope**: Implement prompt engineering for strict factual grounding, call the LLM API, extract citation tokens (`[SOURCE_ID]`), and programmatically validate citations against retrieved evidence records.
- **Concepts to Understand**:
  - *Grounded Prompting*: Forbidding the model from using prior knowledge outside the provided context documents.
  - *Citation Contract*: Enforcing that every assertion maps to an explicit evidence block.
  - *Hallucination Mitigation*: Programmatically stripping or flagging citation IDs that the LLM invented or that do not exist in the retrieved context.
- **Acceptance Criteria**:
  - [ ] `GeneratorService` in `backend/app/services/generator.py` constructs context blocks with explicit `[EVIDENCE RECORD <source_id>]` headings.
  - [ ] LLM system prompt enforces citation markers like `[ALERT-201]`, explicit uncertainty flags, and handling of unproven hypotheses.
  - [ ] Post-processor verifies all citation tags against retrieved IDs.
  - [ ] Unit tests in `tests/test_generator.py` test:
    - Normal citation extraction and linking.
    - Hallucinated citation detection (e.g. LLM invents `SLACK-999`).
    - Explicit statement when context is empty or insufficient.

---

## Milestone 6: FastAPI Integration & End-to-End Workflow
- **Scope**: Wire together ingestion, timeline, retrieval, and generation into complete FastAPI routes. Add error handling, CORS, and request logging.
- **Concepts to Understand**:
  - *FastAPI Dependency Injection*: Using `Depends()` for database connections and configuration.
  - *CORS (Cross-Origin Resource Sharing)*: Allowing the Vite frontend (`localhost:5173`) to call the FastAPI backend (`localhost:8000`).
  - *End-to-End Testing*: Simulating a complete user workflow via `TestClient`.
- **Acceptance Criteria**:
  - [ ] Full REST API operational:
    - `POST /api/incidents/ingest`: Ingests dataset.
    - `GET /api/incidents`: Lists incidents.
    - `GET /api/incidents/{id}/timeline`: Gets deterministic timeline.
    - `POST /api/incidents/{id}/query`: Answers questions with citations.
    - `GET /api/incidents/{id}/events/{source_id}`: Gets event details.
  - [ ] Integration tests in `tests/test_api.py` verify full request-response cycles.

---

## Milestone 7: React + TypeScript Frontend (Timeline + Chat + Citations)
- **Scope**: Build the user interface with React, TypeScript, and Vite. Features include an incident selector, interactive timeline with color-coded source badges, a conversational investigation chat, clickable citation chips, and an event inspection slide-over drawer.
- **Concepts to Understand**:
  - *Component Architecture*: Separating stateful page containers from reusable UI components.
  - *Clickable Citation Anchoring*: How clicking a citation badge `[ALERT-201]` interacts with state to highlight an event or open a details drawer.
  - *Responsive Layout*: Splitting the view into a chronological timeline column and an investigation Q&A column.
- **Acceptance Criteria**:
  - [ ] Frontend initializes cleanly with `npm run dev`.
  - [ ] Timeline renders events chronologically with clear visual differentiation (Slack messages in purple/blue, Alerts in red/amber, Deployments in green).
  - [ ] Chat panel allows user to submit questions (including quick prompt suggestions for the 5 key questions).
  - [ ] Generated answers display clickable citation badges.
  - [ ] Clicking a citation badge opens the Event Inspector Drawer showing raw content and structured payload.

---

## Milestone 8: Demo Polish, Evaluation Benchmarking & Final Walkthrough
- **Scope**: Polish UI/UX, verify performance, run the full retrieval evaluation benchmark, document setup steps in `README.md`, and record or script the hackathon demo walkthrough.
- **Concepts to Understand**:
  - *Hackathon Demo Storytelling*: How to present the problem, the architectural solution, the deterministic timeline guarantee, and live Q&A with verifiable citations.
- **Acceptance Criteria**:
  - [ ] Clean `README.md` with step-by-step setup and quickstart instructions.
  - [ ] Automated script `python scripts/run_eval.py` that runs the evaluation cases and prints a clean benchmark report with hit rates and citation validity.
  - [ ] End-to-end demo flow runs smoothly without errors.

