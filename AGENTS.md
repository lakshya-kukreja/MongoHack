# AGENTS.md — AI & Developer Collaboration Guidelines

## 1. Project Philosophy & Constraints

This repository hosts **Incident Timeline Investigator**, a RAG-powered post-incident analysis tool built by a team mastering RAG, MongoDB Vector Search, and incident investigation.

To keep the codebase maintainable, debuggable, and educational, any AI coding assistant or human contributor **must strictly adhere to the following rules**:

### 🚫 Core Anti-Patterns (Strictly Forbidden)
1. **NO Heavy Agent Frameworks**: Do NOT introduce LangChain, LangGraph, LlamaIndex, AutoGen, CrewAI, or complex multi-agent frameworks. The entire RAG pipeline must be implemented using clean, idiomatic Python with direct API calls (e.g. OpenAI / Google Gemini SDK or `httpx`), Pydantic models, and direct `pymongo` driver calls.
2. **NO Hallucinated Citations**: The LLM must NEVER invent a source identifier (like `SLACK-999` or `ALERT-999`) or guess event IDs. All citations must be programmatically verified against the retrieved set before rendering.
3. **NO LLM-Based Sorting**: The LLM must NEVER be trusted to determine chronology or sort events. Timeline ordering is 100% deterministic, computed by sorting ISO-8601 timestamps in Python or MongoDB.
4. **NO Silent Overwrites**: Never blindly replace entire files or wipe test cases without understanding why they exist.
5. **NO Hardcoded Secrets**: Never commit API keys, connection strings, or sensitive tokens. Always use `.env` via `pydantic-settings`.
6. **NO Unilateral Contract Changes**: NEVER alter shared API endpoint paths, request/response schemas, or TypeScript types without explicit mutual agreement among Person 1, Person 2, and Person 3.
7. **NO Unauthorized Git Actions**: NEVER run `git commit`, `git push`, `git merge`, `git checkout`, or `git branch` without explicit user permission. Git state changes belong entirely to the human developers.
8. **NO Brittle Cloud CI Dependencies**: Unit and integration test suites in `tests/` must run 100% offline using mocked embedding models, mock LLM calls, and in-memory MongoDB fixtures. Live cloud API calls belong only in optional live test suites or demo scripts when real credentials are provided.

---

## 2. Team Structure, File Ownership & Branching

The project is developed by a three-person team working with clear boundaries:

| Role | Primary Domain | Owned Paths | Working Branch | Responsibilities |
|---|---|---|---|---|
| **Person 1** | Backend & RAG | `backend/`, backend test suites (`tests/test_api*.py`, `tests/test_storage*.py`, `tests/test_ingestion.py`, `tests/test_timeline.py`, `tests/test_health.py`, `tests/test_embeddings.py`, `tests/test_retrieval.py`, `tests/test_generator.py`) | `backend-dev` | FastAPI endpoints, backend architecture, MongoDB Atlas integration, ingestion, embeddings, `$vectorSearch`, timeline sorting, RAG generator, backend pytest suite. |
| **Person 2** | Frontend & Integration | `frontend/`, frontend tests (`frontend/src/test/`) | `frontend` | React + TypeScript + Vite app, timeline UI, chat interface, citation chips, event drawer, local mock API integration, client error/loading states, frontend testing. |
| **Person 3** | Data & Evaluation | `data/`, evaluation benchmarks, retrieval eval suite (`tests/test_retrieval_eval.py`, `scripts/run_eval.py`, eval reports) | `backend-dev` (eval fixtures) | Realistic incident datasets, benchmark evaluation queries with ground-truth source IDs, reproducible retrieval evaluation harness, measuring Hit Rate@K, MRR, retrieval latency, citation correctness, testing insufficient and contradictory evidence scenarios, coordinating retrieval interfaces with Person 1 without rewriting the backend pipeline. |
| **Shared** | Architecture & Contracts | `spec.md`, `AGENTS.md`, `backlog.md` | Coordinated | Joint ownership across all 3 developers. Modifying shared contracts requires agreement from all relevant owners. |

### Collaboration Rules:
1. **Respect File Ownership**: Do not modify files owned by another developer without explicit instruction. Never introduce sweeping cross-cutting refactors touching frontend and backend simultaneously.
2. **Inspect Before Editing**: Agents MUST inspect and read existing code before proposing or making edits. Never generate replacements based on assumptions.
3. **Parallel Frontend Development via Mocks**: Person 2 is decoupled from backend completion by utilizing mock responses conforming to `spec.md` (`frontend/src/mocks/`). Backend delays do not block frontend development.
4. **Data & Evaluation Coordination**: Person 3 defines ground-truth datasets and evaluation benchmarks conforming to schemas in `spec.md`, coordinating interfaces with Person 1 without independently rewriting the backend pipeline.
5. **Branch Isolation**:
   - Person 1 works on `backend-dev`.
   - Person 2 works on `frontend`.
   - Person 3 provides datasets and benchmarks on `backend-dev` (or designated evaluation branch).
   - `main` is protected trunk. Branch switching, merging, and commits are strictly human-supervised.
6. **Mandatory Incremental Backlog Updates**:
   - Mark the task `IN PROGRESS` in `backlog.md` before starting implementation.
   - Update `backlog.md` immediately when a task is completed and its acceptance criteria are verified.
   - Mark blocked tasks `BLOCKED`, recording the reason and next action.
   - Add newly discovered tasks as soon as they are identified.
   - Never wait until the end of the session to update the backlog.
   - Update `spec.md` when confirmed requirements, schemas, or API contracts change.
   - Update `AGENTS.md` when standing rules or team ownership change.

The codebase is organized into distinct, single-responsibility modules:

```
backend/
├── app/
│   ├── api/             # FastAPI routes (HTTP handling, request/response validation)
│   ├── core/            # Config, settings, logging, MongoDB client connection
│   ├── models/          # Pydantic schemas (EventRecord, QueryRequest, QueryResponse, Citation)
│   ├── services/
│   │   ├── ingestion.py # Ingests JSON/JSONL, parses into EventRecord models
│   │   ├── embeddings.py# Computes vector embeddings (OpenAI / Gemini)
│   │   ├── storage.py   # MongoDB Atlas CRUD & index management
│   │   ├── timeline.py  # Deterministic timeline sorting, windowing, filtering
│   │   ├── retrieval.py # MongoDB $vectorSearch execution + pre-filtering
│   │   └── generator.py # Prompt formulation, LLM call, citation verification
│   └── main.py          # FastAPI application factory & lifespan
frontend/                # React + Vite + TypeScript single-page app (owned by Person 2)
data/                    # Local demo incident JSON/JSONL and eval benchmark files (owned by Person 3)
tests/                   # Pytest suite (unit, integration, storage, retrieval evaluations)
```

### Module Contracts:
- `ingestion.py`: Accepts raw JSON/JSONL and outputs validated `EventRecord`s. Must preserve source timestamps and unique `source_id`.
- `embeddings.py`: Provides `get_embedding(text: str) -> list[float]` and batch variants. Must handle batching and rate limiting gracefully.
- `storage.py`: Encapsulates all `pymongo` operations. No raw Mongo queries in API routes.
- `timeline.py`: Pure deterministic functions. Input: list of records or query filters. Output: sorted, filtered list of events.
- `retrieval.py`: Orchestrates `$vectorSearch` with metadata pre-filtering (by `incident_id`).
- `generator.py`: Formats context, calls LLM, extracts citation tokens, validates them against retrieved IDs, and returns a structured response.
- `tests/test_retrieval_eval.py`: Reproducible retrieval-evaluation harness computing Hit Rate@K, MRR, and citation precision.

---

## 3. Coding Standards & Conventions

### Python / Backend (Person 1)
- **Python Version**: 3.12+
- **Type Hints**: Mandatory on all function signatures (`def search(query: str, limit: int = 10) -> list[EventRecord]:`).
- **Validation**: Use Pydantic v2 for all request/response schemas and domain models.
- **Async vs Sync**: FastAPI route handlers should be async. Pymongo operations should use `motor` or synchronous `pymongo` wrapped properly.
- **Error Handling**: Use explicit `HTTPException` with helpful error messages. Do not let unhandled 500 errors leak stack traces to the client. Upstream provider timeouts (OpenAI/Gemini) must map to HTTP 504 (Gateway Timeout), and rate limits / upstream failures must map to HTTP 503 (Service Unavailable).
- **Docstrings**: Include concise Google-style docstrings explaining *why* a function exists and what inputs/outputs it expects.
- **Offline Mocking**: Embedding generation and LLM calls in test suites must default to deterministic mocks when API keys are empty or tests are executed in CI.

### Frontend (React + TypeScript) (Person 2)
- **Node Version**: v20+ / v22+
- **Routing**: TanStack Router with file-based routing.
- **State Management**: Simple React hooks (`useState`, `useEffect`, `useMemo`, `useCallback`) or lightweight context. No Redux or heavy state machinery.
- **Styling**: Tailwind CSS for clean, readable component styling.
- **Component Separation**:
  - `TimelineView`: Renders events sorted by time with type badges (`slack`, `alert`, `deploy`).
  - `ChatInterface`: Q&A panel with quick prompt presets, chat history, and streaming/message bubbles.
  - `CitationChip`: Clickable chip linking to an event on the timeline with unverified citation tooltips.
  - `EventDrawer`: Slide-over sheet showing raw content, metadata, and structured payload for any clicked event.
  - `DashboardView`: Overview of active incidents and quick stats.

### Data & Evaluation (Person 3)
- **Data Integrity**: All incident records must feature canonical UTC ISO-8601 timestamps and unique `source_id`s.
- **Benchmark Coverage**: Golden queries must define expected IDs, acceptable supplementary IDs, unacceptable hallucinated IDs, and criteria for handling unproven hypotheses and negative evidence.
- **Evaluation Metrics**: Hit Rate@5, Mean Reciprocal Rank (MRR), query latency, and citation precision.

---

## 4. Definition of Done (DoD) for Any Task

Before any feature, bugfix, or refactor is considered complete:
1. **Existing Code Inspected**: Existing files and surrounding logic must be reviewed before applying edits.
2. **Relevant Tests Pass**:
   - Backend tasks: Unit and integration tests must run with `backend/.venv/bin/pytest tests/` and exit with 0 errors.
   - Frontend tasks: Typecheck (`npm run build` or `npx tsc`) and test suite (`npm test`) pass without errors.
   - Evaluation tasks: Retrieval evaluation benchmark (`tests/test_retrieval_eval.py`) passes with expected source IDs found in top-K results.
3. **Deterministic Timeline Guaranteed**: For backend changes, tests must verify that events remain ordered strictly chronologically regardless of ingestion sequence.
4. **Citation Verification Covered**: For generator changes, tests must verify that hallucinated citation IDs in LLM outputs are detected and rejected into `unverified_citations`.
5. **No Regressions in Evaluation Cases**: Golden benchmark queries must meet Hit Rate@5 = 100% and citation precision = 100%.
6. **No Secret Leakage**: Confirm `.env` or sensitive credentials are never tracked or committed.
7. **Post-Task Summary Provided**: The contributor or agent MUST provide an explicit summary of all modified/created files, detailing the exact nature of the change, test verification results, and any open decisions requiring user review.

---

## 5. How to Run & Verify

### Backend (Person 1)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Running Backend Tests
```bash
# Run all backend unit & integration tests
backend/.venv/bin/pytest tests/ -v

# Run retrieval evaluation benchmarks only
backend/.venv/bin/pytest tests/test_retrieval_eval.py -v
```

### Frontend (Person 2)
```bash
cd frontend
npm install
npm run dev      # Starts Vite dev server (port 5173)
npm test         # Runs Vitest unit & routing tests
npm run build    # Validates TypeScript & builds production bundle
```

### Data Evaluation Benchmark (Person 3)
```bash
# Run automated retrieval & citation evaluation benchmark
python scripts/run_eval.py
```
