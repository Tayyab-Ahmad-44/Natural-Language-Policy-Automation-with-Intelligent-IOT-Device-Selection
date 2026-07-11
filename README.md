# Natural Language Policy Automation with Intelligent IoT Device Selection

A system that turns plain-English automation rules into executable IoT control flows. You
describe what you want in natural language (or speak it), and the system uses an LLM to pick
the right devices and capabilities, build a dependency-aware execution graph (DAG), detect
conflicts with existing rules, and run it - on a schedule, on demand, or in response to live
sensor events.

## What it does

- **Natural-language to execution DAG.** A policy like *"At 11 PM lock the front door, then once
  it's locked arm the camera to record for 60s, and turn off all lights"* is parsed by an LLM
  into a graph of nodes with dependencies, conditions (`on_success`, value comparisons), and
  per-node failure handling (`ignore` / `halt_branch` / `skip_dependents`).
- **Intelligent device selection.** The LLM is given the live device catalog (each device's
  capabilities, HTTP method, and input schema) and maps the request onto the actual capabilities
  available.
- **Tasks to many policies.** A higher-level task description is automatically broken down into
  multiple coordinated policies.
- **Conflict detection.** A cheap deterministic pre-filter (overlapping time windows + shared
  devices) feeds an LLM judge that classifies pairs as contradiction / redundancy / overlap and
  suggests a resolution, with a rule-based fallback when the LLM is unavailable.
- **DAG execution engine.** Runs independent nodes in parallel and dependent ones in order,
  evaluating conditions against upstream responses. Every run and step is persisted.
- **Real-time streaming.** Execution can be streamed step-by-step to the UI over Server-Sent
  Events (SSE).
- **Scheduling & event triggers.** A background scheduler ticks every 15s (supporting one-shot,
  windowed, and repeat-interval policies). A separate SSE manager subscribes to sensor streams
  and triggers matching policies on incoming readings.
- **Camera / VLM analysis.** Policy nodes (and a standalone test panel) can run vision analysis
  on an image or video using Gemini vision model, returning normalized JSON usable in
  DAG conditions.
- **Voice input.** Policies can be dictated; audio is transcribed via Groq Whisper.
- **Auto-discovery.** Point the system at an arbitrary device-catalog endpoint and the LLM maps
  the response into the Device/Capability schema for bulk import.

## Architecture

```
frontend/  Next.js 16 + React 19 UI (React Flow DAG visualizer, Tailwind)
backend/   FastAPI app, SQLAlchemy models, LLM/VLM integration, execution engine
```

### Backend (`backend/`)

| File | Responsibility |
|------|----------------|
| `application.py` | FastAPI app, all REST/SSE endpoints, scheduler & SSE manager loops |
| `models.py` | SQLAlchemy models: Device, Capability, Policy, Task, ExecutionRun/Step, SensorReading |
| `database.py` | Engine/session setup (PostgreSQL) |
| `schemas.py` | Pydantic request/response schemas |
| `llm.py` | Policy parsing, task breakdown, device mapping (via `llm_provider`) |
| `llm_provider.py` | Selects the chat-completion backend (Groq or OpenAI) from `.env` |
| `dag_utils.py` | DAG validation, topological levels, flat-to-DAG migration |
| `executor.py` | Executes a policy's DAG (parallel/sequential/conditional), persists runs |
| `conflicts.py` | Conflict pre-filter + LLM judge (via `llm_provider`) |
| `vision.py` | VLM image/video analysis (Gemini / Groq) |
| `mock_devices.py` | Standalone mock IoT device server for local testing |

### Frontend (`frontend/`)

Next.js App Router. Pages: **Devices**, **Policies**, **Tasks**, **Executions**, **Schedule**
(plus login/signup scaffolding). DAGs are rendered with `@xyflow/react` + `dagre` layout.
Components include `DAGView`, `ConflictCard`, `VlmTestPanel`, `VoiceButton`, and `Navbar`.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL (`psycopg`), Uvicorn, httpx
- **AI:** Groq or OpenAI (chat-completion LLM, selectable via `.env`), Groq Whisper, Google Gemini
  / Groq vision models
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, React Flow, axios

## Getting started

### Prerequisites

- Python 3.11+ and a running PostgreSQL instance
- Node.js 18+
- A Groq API key or an OpenAI API key (whichever `LLM_PROVIDER` you choose), and a Gemini API
  key if you use the Gemini VLM provider

### 1. Backend

```bash
cd backend
python -m venv env
source env/Scripts/activate      # Windows (Git Bash); use env\Scripts\activate on cmd/PowerShell
pip install -r requirements.txt
```

Create `backend/.env`:

```env
# LLM provider for policy parsing, task breakdown, device mapping, and
# conflict judging. Defaults to groq if unset.
LLM_PROVIDER=groq              # or openai
GROQ_API_KEY=your_groq_key
# OPENAI_API_KEY=your_openai_key   # required if LLM_PROVIDER=openai
# LLM_MODEL=llama-3.3-70b-versatile  # override the provider's default model

# Either a full URL...
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
# ...or individual parts (used if DATABASE_URL is unset):
# DB_USER=postgres
# DB_PASSWORD=postgres
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=postgres

# Optional VLM settings
GEMINI_API_KEY=your_gemini_key
VLM_PROVIDER=gemini            # or groq
# VLM_MODEL=gemini-3.5-flash
```

`LLM_PROVIDER` picks the SDK (`groq` or `openai`); each provider reads its own API key and falls
back to a sensible default model (`llama-3.3-70b-versatile` for Groq, `gpt-4o-mini` for OpenAI)
unless `LLM_MODEL` is set. This is independent of `VLM_PROVIDER`, which only controls camera/video
scene analysis.

Run it (tables are created automatically on startup):

```bash
uvicorn application:app --reload --host 0.0.0.0 --port 8000
# or, from the repo root:  make run-backend
```

Interactive API docs are then available at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# or, from the repo root:  make run-frontend
```

The UI runs on `http://localhost:3000`.

### 3. (Optional) Mock device server

To exercise the executor without real hardware, run the bundled mock IoT server, then register
its endpoints as devices:

```bash
cd backend
uvicorn mock_devices:app --port 8001
```

## Key API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET/POST/PUT/DELETE` | `/api/devices/` | Manage devices & capabilities |
| `POST` | `/api/devices/discover`, `/api/devices/bulk` | LLM auto-discovery & bulk import |
| `POST` | `/api/policies/preview` | Parse NL to DAG (no save) + conflicts |
| `POST` | `/api/policies/` | Create policy from natural language |
| `POST` | `/api/policies/{id}/execute` | Run a policy's DAG |
| `POST` | `/api/policies/{id}/execute/stream` | Run with live SSE step events |
| `POST` | `/api/tasks/` | Break a task into multiple policies |
| `GET` | `/api/executions/`, `/api/executions/{id}` | Execution history & detail |
| `POST` | `/api/transcribe` | Voice to text (Whisper) |
| `POST` | `/api/vlm/test` | One-off image/video VLM analysis |
| `POST` | `/api/cron/tick` | Manually trigger a scheduler tick |

## Evaluation harness (`eval/`)

A standalone, deterministic (no-LLM-judge) scoring harness that produces hard accuracy numbers
for the NL→DAG compiler and the two-stage conflict detector. Fully isolated from `backend/` —
it imports the real `schemas.ExecutionDAG`/`dag_utils` contracts rather than duplicating them, but
nothing in `backend/` imports from it.

- **`eval/catalogs/`** — 5 device catalogs (home, factory, hospital, farm, retail), in the same
  shape the app feeds the LLM.
- **`eval/scenarios/dag/`** — 10 labelled NL→DAG scenarios (expected nodes, edges, conditions,
  failure modes), tagged `single_node` / `multi_node` / `conditional` / `parallel` / `scheduled`.
- **`eval/scenarios/conflicts/`** — 5 labelled conflict scenarios (~24 candidate pairs) covering
  contradiction / redundancy / overlap / none.
- **`eval/scoring/`** — the scorers themselves: node/edge alignment by canonical
  `(device, capability)` identity (with arg-similarity and topological-position disambiguation),
  precision/recall/F1, condition and failure-mode accuracy, strict exact-structural-match rate,
  per-class conflict P/R/F1, and pre-filter recall measured in isolation.
- **`eval/run.py`** — the CLI runner: aggregates metrics overall and per tag, measures structural
  stability across repeated generations, and writes a JSON report.
- **`eval/tests/`** — a 65-case pytest suite for the scorers, fully offline (no network calls).

```bash
cd backend
pip install -r ../eval/requirements-dev.txt   # adds pytest

# Run the scorer's own test suite (no API key / network needed)
python -m pytest ../eval/tests -v
```

`eval.run` is a package entry point and must be invoked with the repo root as the working
directory (not `backend/`):

```bash
cd ..    # repo root

# Run the full harness against the real LLM_PROVIDER configured in backend/.env
python -m eval.run --repeats 5

# Or an offline wiring smoke test (no network calls at all)
python -m eval.run --mock
```

`eval/run.py` reads whichever `LLM_PROVIDER` is configured in `backend/.env`, so switching between
Groq and OpenAI also changes which model the harness evaluates.

