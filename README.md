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
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Required variables:
- `APP_SECRET`: Secret for session and password hashing

Optional variables (defaults shown):
- `GROQ_API_KEY` (optional; enables live LLM instead of the mock fallback)
- `GROQ_MODEL=llama-3.3-70b-versatile`
- `DATABASE_URL=sqlite:///./ops_autopilot.db`
- `DEFAULT_LOCALE=fr`
- `LLM_PROVIDER=mock` (`mock` or `groq`)

### 3. Run the Application

**CLI (no UI, mock LLM works offline):**
```bash
python -m graph.cli run --preset lumea --non-interactive
python -m graph.cli run --preset saas
python -m graph.cli run --name "Acme" --sector D2C --free-text "Instagram DMs: ~50/day, 2 min each, highly repetitive."
```
Each run pauses at the human review (`a`/`m`/`r`), persists state to
`ops_autopilot_checkpoints.db` (`--checkpoint-db` to change), and resumes the same
thread via LangGraph's `interrupt` / `Command(resume=...)`. Use `--groq-api-key` /
`--groq-model` to enable live LLM calls.

**Streamlit UI (construction order step 5, not yet implemented):**
```bash
streamlit run ui/app.py
```

## Architecture

```
ops-autopilot/
  domain/           # Pure business rules (no LangGraph / CrewAI / Streamlit)
    models.py       # Brand, Task, Score, Recommendation, Assumptions
    scoring.py      # ROI formulas - unit-testable without LLM
    formulas.md     # Human-readable formula docs

  app/              # Use cases
    run_analysis.py
    resume_review.py
    list_history.py

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
  db/               # SQLite repositories; Postgres-ready schema [step 6]
  ui/               # Thin Streamlit layer [step 5]
  profiles/         # Lumea (D2C), SaaS presets
  tests/
  docs/
```

## Development

### Running Tests

```bash
pytest
```

### Domain Layer Tests

```bash
pytest tests/domain/
```

### Graph Integration Tests

```bash
pytest tests/graph/
```

## Construction order

Per design spec `docs/superpowers/specs/2026-08-01-ops-autopilot-design.md`:

1. ✅ Domain layer (models, scoring, formulas) + presets
2. ✅ LangGraph CLI with prints, mocked LLM fallback (offline)
3. ✅ CrewAI inside `deep_dive` (testable in isolation; degrades offline)
4. ✅ Checkpointer + `interrupt` / `Command(resume=...)` (SQLite, `--checkpoint-db`)
5. ⏳ Streamlit UI
6. ⏳ Auth, history, DB repositories

## Interview Demo

~6 minutes: problem → Lumea input → live analysis / crew → human checkpoint (edit rate, approve) → final report → trade-offs.

Product rule: **the agent never alone finalizes figures that commit budget** - human review is mandatory.

## License

Internal project for demonstration purposes.
