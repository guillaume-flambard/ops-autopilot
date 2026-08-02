# Ops Autopilot

An assistant that analyzes a brand's operations, quantifies where time and money go, and recommends *what to automate first* — with a concrete implementation plan and estimated ROI.

## Features

- **End-to-end analysis**: ingest → map → score → deep-dive (top 3) → human review → executive report
- **Transparent assumptions**: Every figure shows its assumptions; no "magic" numbers
- **Human in the loop**: Must approve/edit/reject before final report
- **Small-team product**: Email/password auth, analysis history, centralized config
- **Bilingual**: FR and EN UI + reports with locale toggle
- **Local LLM**: Uses Ollama (Llama 3.2 3B) with Groq fallback
- **Clean architecture**: Domain rules readable without opening LangGraph

## Quick Start

### Prerequisites

- Python 3.11+
- Ollama (for local LLM)
- Groq API key (optional, as fallback)

### 1. Install Ollama

**On Mac:**
```bash
# Using Homebrew
brew install ollama

# Or download from https://ollama.ai
```

**Start Ollama:**
```bash
ollama serve
```

**Pull Llama 3.2 3B model:**
```bash
ollama pull llama3.2:3b
```

**Test Ollama:**
```bash
ollama run llama3.2:3b "Hello, test response"
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Required variables:
- `APP_SECRET`: Secret for session and password hashing
- `GROQ_API_KEY`: Your Groq API key (fallback)

Optional variables (defaults shown):
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_MODEL=llama3.2:3b`
- `DATABASE_URL=sqlite:///./ops_autopilot.db`
- `DEFAULT_LOCALE=fr`
- `LLM_PROVIDER=ollama`

### 4. Run the Application

**Streamlit UI:**
```bash
streamlit run ui/app.py
```

**CLI (for testing):**
```bash
python graph/cli.py run --preset lumea
```

## Architecture

```
ops-autopilot/
  domain/           # Pure business rules (no LangGraph / CrewAI / Streamlit)
    models.py       # Brand, Task, Score, Recommendation, Assumptions
    scoring.py      # ROI formulas — unit-testable without LLM
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
    agents.py
    tasks.py
    run_deep_dive.py

  llm/              # Ollama + Groq client + retry + fallback
  db/               # SQLite repositories; Postgres-ready schema
  ui/               # Thin Streamlit layer
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

## Interview Demo

~6 minutes: problem → Lumea input → live analysis / crew → human checkpoint (edit rate, approve) → final report → trade-offs.

Product rule: **the agent never alone finalizes figures that commit budget** — human review is mandatory.

## License

Internal project for demonstration purposes.
