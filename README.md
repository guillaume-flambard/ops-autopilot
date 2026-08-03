# Ops Autopilot

An assistant that analyzes a brand's operations, quantifies where time and money go, and recommends *what to automate first* - with a concrete implementation plan and estimated ROI.

## Features

- **End-to-end analysis**: ingest → map → score → deep-dive (top 3) → human review → executive report
- **Transparent assumptions**: Every figure shows its assumptions; no "magic" numbers
- **Human in the loop**: Must approve/edit/reject before final report
- **Small-team product**: Email/password auth, analysis history, centralized config
- **Bilingual**: FR and EN UI + reports with locale toggle
- **LLM**: Groq free tier with retry/backoff, plus a deterministic offline fallback (mock)
- **Clean architecture**: Domain rules readable without opening LangGraph

## Quick Start

### Prerequisites

- Python 3.11+
- Groq API key (optional; without it the app runs in offline mock mode)

### 1. Install Python Dependencies

```bash
make install          # uv venv + pinned deps from requirements.txt
cp .env.example .env  # edit with your settings (APP_SECRET, GROQ_API_KEY, ...)
```

Optional variables (defaults shown):
- `GROQ_API_KEY` (optional; enables live LLM instead of the mock fallback)
- `GROQ_MODEL=llama-3.3-70b-versatile`
- `DATABASE_URL=sqlite:///./ops_autopilot.db`
- `DEFAULT_LOCALE=fr`
- `LLM_PROVIDER=mock` (`mock` or `groq`)

### 2. Run the Application

```bash
make run    # Streamlit UI
make demo   # offline CLI demo arc (mock LLM)
make test   # full test suite
make reset  # wipe local SQLite DBs (app + checkpoints)
```

**CLI (no UI, mock LLM works offline):**
```bash
.venv/bin/python -m graph.cli run --preset lumea --non-interactive
.venv/bin/python -m graph.cli run --preset saas
.venv/bin/python -m graph.cli run --name "Acme" --sector D2C --free-text "Instagram DMs: ~50/day, 2 min each, highly repetitive."
```
Each run pauses at the human review (`a`/`m`/`r`), persists state to
`ops_autopilot_checkpoints.db` (`--checkpoint-db` to change), and resumes the same
thread via LangGraph's `interrupt` / `Command(resume=...)`. Use `--groq-api-key` /
`--groq-model` to enable live LLM calls.

**Streamlit UI (construction order steps 5-6):**
```bash
make run   # or: .venv/bin/streamlit run ui/app.py
```
Register/login (email/password, bcrypt-hashed) → input form (preset or custom
brand + assumptions) → live timeline → human review (Approver / Modifier /
Rejeter) → final report, persisted to SQLite and listed on the Historique page.
Checkpoints persist in `ops_autopilot_checkpoints.db`, so a page refresh resumes
the same thread.

## Architecture

```
ops-autopilot/
  domain/           # Pure business rules (no LangGraph / CrewAI / Streamlit)
    models.py       # Brand, Task, Score, Recommendation, Assumptions
    scoring.py      # ROI formulas - unit-testable without LLM
    formulas.md     # Human-readable formula docs

  app/              # Use-case layer (shared by CLI and UI) [step 7]
    run_analysis.py # build_runtime, run_analysis, resume_review (single code path)
    presets.py      # load_preset from profiles/*.json
    list_history.py # history page use case

  graph/            # LangGraph adapter
    state.py
    nodes/          # ingest, map_tasks, score, deep_dive, check_data, human_review, report
    edges.py
    build.py        # Compile + checkpointer

  crew/             # CrewAI adapter (called ONLY by deep_dive)
    agents.py       # Ops Analyst -> ROI Estimator -> Solution Architect
    tasks.py
    run_deep_dive.py

  llm/              # Groq client + retry/backoff + deterministic mock fallback
    client.py
    prompts.py
  graph/checkpointer.py # JsonPlus serde + Pydantic-safe SQLite saver [step 4]
  graph/driver.py    # Shared stream-until-interrupt driver (CLI + UI)
  db/               # SQLite repositories; Postgres-ready schema (users, analyses)
    models.py       # SQLAlchemy 2.0 ORM (User, Analysis)
    repo.py         # auth + analysis CRUD, cached engines, checkpoint path
  ui/               # Thin Streamlit layer [steps 5-6]
    app.py          # Login -> form -> review -> report + history page
  profiles/         # Lumea (D2C), SaaS presets
  tests/
  docs/
```

## Development

### Running Tests

```bash
pytest
```

### Coverage

```bash
pytest --cov=domain --cov=graph --cov=crew --cov=llm --cov=app --cov=db --cov-report=term
```

Targets (design spec, section 9): domain 90%+, graph 70%+, crew 50%+. CI
enforces a global floor of 75% (`.github/workflows/ci.yml`).

### Domain Layer Tests

```bash
pytest tests/domain/
```

### Graph Integration Tests

```bash
pytest tests/graph/
```

### E2E + Eval Suite

```bash
pytest tests/integration/   # full pipeline vs real SQLite + on-disk checkpointer
pytest tests/llm/test_eval_map_tasks.py  # ground-truth parser scoring (10 cases, floor 90%)
```

## Deployment

Mono-team production: Streamlit Cloud or a single VPS, daily SQLite backup,
Postgres-ready schema. Full guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Construction order

Per design spec `docs/superpowers/specs/2026-08-01-ops-autopilot-design.md`:

1. ✅ Domain layer (models, scoring, formulas) + presets
2. ✅ LangGraph CLI with prints, mocked LLM fallback (offline)
3. ✅ CrewAI inside `deep_dive` (testable in isolation; degrades offline)
4. ✅ Checkpointer + `interrupt` / `Command(resume=...)` (SQLite, `--checkpoint-db`)
5. ✅ Streamlit UI (form, timeline, review Approve/Edit/Reject, final report)
6. ✅ Auth (bcrypt), analysis history, DB repositories (SQLAlchemy, SQLite/Postgres-ready)
7. ✅ Use-case layer (`app/`): CLI and UI drive the graph through one code path
8. ✅ Coverage targets + CI (`.coveragerc`, pytest-cov, GitHub Actions; global floor 75%, spec targets per layer)
9. ✅ Live LLM path validated (Groq + CrewAI): httpx pinned <0.28, robust JSON extraction for chat-model output
10. ✅ v1 finishing: removed legacy Ollama, direct `bcrypt` (no passlib), Pydantic V2 config, hermetic test env (`tests/conftest.py`), end-to-end integration tests, eval suite v1.1 (ground-truth task parser, 10 cases)

## Interview Demo

~6 minutes, all offline-mockable except the live LLM pass:

1. `cp .env.example .env` and set `GROQ_API_KEY=...`, `LLM_PROVIDER=groq` (or skip both for the deterministic offline mock).
2. `make run` → register a test account.
3. Load the **Lumea** preset: watch ingest → map_tasks → score stream in the live timeline (Groq-backed if configured, mock otherwise).
4. The run pauses at **human review**: edit the "Instagram DMs" rate up, then Approve.
5. Read the **final executive report** (sector-aware), then check the Historique page for the persisted analysis.
6. Trade-offs: highlight the two golden rules below and the transparent assumptions behind every figure.

Product rules to call out:
- **the agent never alone finalizes figures that commit budget** - human review is mandatory;
- **money only via `domain/scoring.py`** - the LLM never invents amounts, it only suggests assumptions the human must accept.

## License

Internal project for demonstration purposes.
