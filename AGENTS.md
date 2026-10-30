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
6. **NO Unilateral Contract Changes**: NEVER alter shared API endpoint paths, request/response schemas, or TypeScript types without explicit mutual agreement between Person 1 and Person 2.
7. **NO Unauthorized Git Actions**: NEVER run `git commit`, `git push`, `git merge`, `git checkout`, or `git branch` without explicit user permission. Git state changes belong entirely to the human developers.

---

## 2. Team Structure, File Ownership & Branching

The project is developed by a two-person team working on separate Git branches:

| Role | Primary Domain | Owned Paths | Responsibilities |
|---|---|---|---|
| **Person 1** | Backend & Database | `backend/`, `data/`, backend tests | FastAPI routes, MongoDB Atlas integration, ingestion, embeddings, `$vectorSearch`, timeline sorting, RAG generator, backend pytest suite. |
| **Person 2** | Frontend & UI | `frontend/`, frontend tests | React + TypeScript + Vite app, timeline components, chat interface, citation chips, event drawer, local mock API integration. |
| **Shared** | Architecture & Contracts | `spec.md`, `AGENTS.md`, `backlog.md` | Joint ownership. Modifying shared contracts requires agreement from both developers. |

### Collaboration Rules:
1. **Respect File Ownership**: Do not modify files owned by the other developer without explicit instruction. Never introduce sweeping refactors that touch both frontend and backend simultaneously.
2. **Inspect Before Editing**: Agents MUST inspect and read existing code before proposing or making edits. Never generate replacements based on assumptions.
3. **Parallel Frontend Development via Mocks**: Person 2 is decoupled from backend completion by utilizing mock responses conforming to `spec.md` (`frontend/src/mocks/`). Backend delays do not block frontend development.
4. **Branch Isolation**: Each developer operates on their own feature branch. Branch switching, merging, and commits are strictly human-supervised.

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
frontend/                # React + Vite + TypeScript single-page app
data/                    # Local demo incident JSON/JSONL files
tests/                   # Pytest suite (unit, integration, retrieval evaluations)
```

### Module Contracts:
- `ingestion.py`: Accepts raw JSON/JSONL and outputs validated `EventRecord`s. Must preserve source timestamps and unique `source_id`.
- `embeddings.py`: Provides `get_embedding(text: str) -> list[float]` and batch variants. Must handle batching and rate limiting gracefully.
- `storage.py`: Encapsulates all `pymongo` operations. No raw Mongo queries in API routes.
- `timeline.py`: Pure deterministic functions. Input: list of records or query filters. Output: sorted, filtered list of events.
- `retrieval.py`: Orchestrates `$vectorSearch` with metadata pre-filtering (by `incident_id`).
- `generator.py`: Formats context, calls LLM, extracts citation tokens, validates them against retrieved IDs, and returns a structured response.

---

## 3. Coding Standards & Conventions

### Python / Backend
- **Python Version**: 3.12+
- **Type Hints**: Mandatory on all function signatures (`def search(query: str, limit: int = 10) -> list[EventRecord]:`).
- **Validation**: Use Pydantic v2 for all request/response schemas and domain models.
- **Async vs Sync**: FastAPI route handlers should be async. Pymongo operations should use `motor` or synchronous `pymongo` wrapped properly.
- **Error Handling**: Use explicit `HTTPException` with helpful error messages. Do not let unhandled 500 errors leak stack traces to the client.
- **Docstrings**: Include concise Google-style docstrings explaining *why* a function exists and what inputs/outputs it expects.

### Frontend (React + TypeScript)
- **Node Version**: v20+ / v22+
- **State Management**: Simple React hooks (`useState`, `useEffect`, `useMemo`, `useCallback`) or lightweight context. No Redux or heavy state machinery.
- **Styling**: Tailwind CSS for clean, readable component styling.
- **Component Separation**:
  - `TimelineView`: Renders events sorted by time with type badges (`slack`, `alert`, `deploy`).
  - `ChatInterface`: Q&A panel with stream or message bubbles.
  - `CitationChip`: Clickable chip linking to an event on the timeline.
  - `EventDrawer`: Slide-over showing raw content and structured payload for any clicked event.

---

## 4. Definition of Done (DoD) for Any Task

Before any feature, bugfix, or refactor is considered complete:
1. **Existing Code Inspected**: Existing files and surrounding logic must be reviewed before applying edits.
2. **Relevant Tests Pass**:
   - Backend tasks: Unit and integration tests must run with `pytest tests/` and exit with 0 errors.
   - Frontend tasks: Typecheck (`npm run build` or `npx tsc`) and component tests pass without errors.
3. **Deterministic Timeline Guaranteed**: For backend changes, tests must verify that events remain ordered strictly chronologically regardless of ingestion sequence.
4. **Citation Verification Covered**: For generator changes, tests must verify that hallucinated citation IDs in LLM outputs are detected and rejected.
5. **No Regressions in Evaluation Cases**: The retrieval evaluation benchmark (`tests/test_retrieval_eval.py`) must pass with expected source IDs found in top-K results.
6. **No Secret Leakage**: Confirm `.env` or sensitive credentials are never tracked or committed.
7. **Post-Task Summary Provided**: The contributor or agent MUST provide an explicit summary of all modified/created files, detailing the exact nature of the change and any open decisions requiring user review.

---

## 5. How to Run & Verify

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run retrieval evaluation benchmarks only
pytest tests/test_retrieval_eval.py -v
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

