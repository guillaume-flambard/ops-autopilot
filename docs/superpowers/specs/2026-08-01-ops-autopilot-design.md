# Ops Autopilot — Design Spec

**Date:** 2026-08-01  
**Status:** Approved for planning  
**Product one-liner:** An assistant that analyzes a brand’s operations, quantifies where time and money go, and recommends *what to automate first* — with a concrete implementation plan and estimated ROI.

---

## 1. Problem & success criteria

### Problem

Mid-size brands waste hours on repetitive work but pick automation targets by gut feel. Leaders need a consultant-grade answer to: *“Where should I put automation effort to save money?”*

### Target persona

E-commerce / digital brand (~10–20 people). Primary demo profile: **Lumea** (D2C cosmetics, Instagram + Shopify + email support). Second profile: **SaaS** (support + onboarding + content ops).

### Success criteria (v1 = finished product + interview-ready demo)

- End-to-end run: ingest → map → score → deep-dive (top 3) → human review → executive report
- Transparent, editable assumptions; no “magic” numbers
- Human must approve/edit/reject before final report
- Small-team product: email/password auth, analysis history, centralized config
- Bilingual UI + reports: **FR and EN** (locale toggle)
- LLM via **Groq free tier**, with rate-limit resilience
- Clean, human-readable architecture (domain rules readable without opening LangGraph)

### Explicit non-goals (v1)

- Multi-tenant SaaS, OAuth, billing
- Fully autonomous budget decisions
- Polished marketing CSS
- Formal eval harness beyond unit/integration fixtures (eval suite = v1.1)

---

## 2. Product decisions (locked)

| Decision | Choice |
| --- | --- |
| Scope | Full brief MVP as a **finished mono-team product**, also usable as a ~6 min interview demo |
| Users | Small team (2–5): auth + history + shared config |
| Auth | Streamlit email + password, local `users` table |
| LLM | Groq free tier |
| Locale | FR + EN toggle |
| Persistence | SQLite in v1, schema ready to migrate to Postgres |
| Orchestration approach | LangGraph pilots; CrewAI only inside `deep_dive`; deterministic scoring in domain code |

---

## 3. Architecture

### Principle

Organize by **business concern**, not by framework. A human should open `domain/scoring.py` and understand every euro figure without reading LangGraph or CrewAI.

### Layout

```
ops-autopilot/
  domain/           # pure business rules (no LangGraph / CrewAI / Streamlit)
    models.py       # Brand, Task, Score, Recommendation, Assumptions
    scoring.py      # ROI formulas — unit-testable without LLM
    formulas.md     # human-readable formula docs

  app/              # use cases
    run_analysis.py
    resume_review.py
    list_history.py

  graph/            # LangGraph adapter
    state.py
    nodes/          # ingest, map_tasks, score, deep_dive, check_data, human_review, report
    edges.py
    build.py        # compile + checkpointer

  crew/             # CrewAI adapter (called ONLY by deep_dive)
    agents.py
    tasks.py
    run_deep_dive.py

  llm/              # Groq client + retry + fallback
  db/               # SQLite repositories; Postgres-ready schema
  ui/               # thin Streamlit layer
  profiles/         # Lumea (D2C), SaaS presets
  tests/
  docs/
```

### Layer diagram

```
UI Streamlit (auth · i18n · assumptions · live steps · review · history)
        │
app/ (use cases)
        │
graph/ LangGraph + checkpointer
  ingest → map_tasks → score → [top ROI?] deep_dive → check_data ⟲
       → human_review (interrupt) → report
        │
        └── deep_dive → crew/ (Ops Analyst → ROI Estimator → Solution Architect)
        │
domain/scoring  (deterministic numbers)
db/ SQLite      (users, profiles, analyses, checkpoints)
llm/ Groq       (map_tasks, crew, report only)
```

### Golden rules

1. **LangGraph pilots everything**; CrewAI is a normal node implementation detail.
2. **Scoring is code**, not LLM output.
3. **Human in the loop** before any final recommendation report; money-touching suggestions always note HITL.
4. Every displayed figure shows its **assumptions**.

---

## 4. Domain model & formulas

### Entities

| Entity | Key fields |
| --- | --- |
| `Assumptions` | `hourly_rate_eur`, `weeks_per_month` (default `4.33`), `locale` (`fr` \| `en`) |
| `BrandProfile` | name, sector, team size, channels, free-text notes, raw/structured tasks |
| `Task` | name, `volume_per_week`, `minutes_per_unit`, `repetitiveness` (1–5), `automatability` (1–5) |
| `ScoredTask` | Task + `hours_per_month`, `eur_per_month`, `etp`, `priority_score`, ROI rank |
| `DeepDive` | substeps, proposed tool, agent flow, main risk, effort, 2–3 week pilot plan |
| `Analysis` | `user_id`, brand snapshot, assumptions, scored tasks, deep dives, `review_status`, report, timestamps |

### Formulas (deterministic)

```
hours_per_month = volume_per_week × (minutes_per_unit / 60) × weeks_per_month
eur_per_month   = hours_per_month × hourly_rate_eur
etp             = hours_per_month / 151.67   # ≈ 35h/week × 52/12

priority_score  = hours_per_month × (repetitiveness / 5) × (automatability / 5)
```

- ROI ranking = descending `priority_score`, tie-break on `eur_per_month`
- Deep-dive runs on **top 3** only (configurable)
- `check_data` loops if `hourly_rate_eur` is missing or ≤ 0

Illustrative numbers (e.g. Lumea table in the product brief) are **fixtures**, not ground truth — always labeled as estimates.

### Persistence (SQLite → Postgres-ready)

Tables:

- `users` — id, email, password_hash, created_at
- `brand_profiles` — id, owner_user_id (nullable for shared presets), payload JSON, name, created_at
- `analyses` — id, user_id, brand_name, assumptions JSON, result JSON, review_status (`pending` \| `approved` \| `edited` \| `rejected`), created_at, updated_at
- LangGraph checkpointer tables (same SQLite file or sibling file — prefer **same DB** for ops simplicity)

Use SQLAlchemy or raw SQL with portable types; avoid SQLite-only features in schema definitions.

---

## 5. Graph flow & human review

### Nodes

1. **`ingest`** — load brand (form or preset) + assumptions into state  
2. **`map_tasks`** — Groq structures `Task[]` when input is free text; pass-through if already structured  
3. **`score`** — call `domain/scoring.py` only  
4. **Conditional edge** — if top-3 eligible → `deep_dive`, else → `check_data`  
5. **`deep_dive`** — `crew/run_deep_dive.py` on top 3; deterministic template fallback on Groq failure  
6. **`check_data`** — if key assumption missing → interrupt to collect it → resume and re-enter `score` (or continue)  
7. **`human_review`** — `interrupt()` with scored table + top-3 deep dives + assumptions  
8. **`report`** — 5-line executive summary + prioritized roadmap; persist `analyses`

### Human review actions

| Action | Behavior |
| --- | --- |
| **Approve** | `Command(resume={"action": "approve"})` → `report` |
| **Edit** | Patch assumptions and/or drop/edit a recommendation → may re-`score` / re-`deep_dive` → review again |
| **Reject** | Mark analysis `rejected`; no final report; keep history row |

### Streaming

Each node emits a short, human-readable step event for the UI timeline (no raw stack traces in the happy path).

### Checkpointer

SQLite checkpointer so Streamlit refresh / multi-step review can resume the same thread id.

---

## 6. CrewAI (deep_dive only)

Sequential crew, shared context:

1. **Ops Analyst** — break task into substeps; mark what is realistically automatable  
2. **ROI Estimator** — apply **domain formulas** using provided assumptions; must not invent hourly rates  
3. **Solution Architect** — tool suggestion, agent flow, primary risk, effort (2–3 week pilot), HITL when money is involved  

Output: structured JSON/Pydantic → graph state.

If Groq rate-limits or fails after retries: use a **degraded deep-dive template** filled from scored metrics + a visible “degraded estimate” badge.

---

## 7. UI (Streamlit)

Thin layer only:

- Login (email / password)
- Locale toggle FR / EN
- Preset picker (Lumea, SaaS) or custom brand form
- Always-visible **assumptions** panel
- Live step timeline during graph stream
- Review screen: Approve / Edit / Reject
- Final report view (table + top 3 + executive summary)
- Team **history** page

UI serves content; no heavy visual design work in v1.

### Screens & flows

1. **Login** — email/password form, register link, locale toggle (top-right)
2. **Dashboard** — new analysis button + history list (columns: brand name, date, status, locale)
3. **New Analysis** — preset picker (Lumea, SaaS) or custom brand form + assumptions panel
4. **Analysis Run** — live step timeline (ingest → map → score → deep-dive → check_data → review)
5. **Human Review** — scored tasks table (sort by ROI), top-3 deep dives, assumptions panel, Approve/Edit/Reject buttons
6. **Final Report** — executive summary, prioritized roadmap, assumptions sidebar, download/export options
7. **History** — list of past analyses with status, brand name, date, quick link to report

### i18n approach

- Python dict for UI strings: `{"fr": {"login": "Connexion", ...}, "en": {"login": "Login", ...}}`
- Report templates: separate FR/EN markdown strings for executive summary and roadmap sections
- LLM prompts switch based on `assumptions.locale`
- Locale stored in user session; persists across analyses

### Assumptions panel

Always visible in analysis flow. Shows:
- `hourly_rate_eur` (editable, validated > 0)
- `weeks_per_month` (editable, default 4.33, validated > 0)
- Calculated totals: total hours/month, total €/month, total ETP

Changes trigger re-scoring (with confirmation dialog to avoid accidental edits).

### State management

- Streamlit session state for: current user, locale, active analysis thread ID, review mode
- LangGraph thread ID stored in session state for resume capability
- Checkpointer enables recovery after page refresh

### Error handling in UI

- Graph errors: show friendly message + step where it failed + retry option
- LLM rate limits: show "waiting for Groq..." with retry countdown
- Validation errors: inline on form fields (e.g., hourly rate must be > 0)

---

## 8. LLM integration (Groq)

### Config (`.env`)

- `GROQ_API_KEY` (required for live LLM paths)
- `APP_SECRET` (session / password hashing pepper)
- `DATABASE_URL` (default `sqlite:///./ops_autopilot.db`)
- `DEFAULT_LOCALE` (`fr` or `en`)
- Optional: `GROQ_MODEL` (pin a supported Groq model id, e.g., `llama-3.3-70b-versatile`)

### Client wrapper

`llm/groq_client.py`:
- Retry with exponential backoff (max 3 retries, base delay 1s, max 10s)
- Rate-limit detection via HTTP 429, wait with jitter (±20% random)
- Fallback to deterministic template when Groq fails (deep-dive degraded mode, report generation with canned template)
- Model selection via config (pin model for demo stability)
- Timeout handling (default 30s per request)

### Usage points

1. **`map_tasks`** — free text → structured `Task[]` (1–5 ratings, volume, minutes)
2. **CrewAI agents** — Ops Analyst, ROI Estimator, Solution Architect prompts
3. **`report`** — executive summary + roadmap narrative (localized)

### Prompt strategy

- System prompts stored as templates with `{locale}` placeholder
- Few-shot examples for task mapping (show structured vs unstructured input)
- Force JSON/Pydantic output where possible via Groq's structured output
- Never ask LLM to compute financial figures — use `domain/scoring.py`
- Prompt templates in `llm/prompts/` directory, FR and EN variants

### Rate-limit resilience

- Streaming: emit step events even if LLM stalls
- Deep-dive degraded mode: if Groq fails, fill from scored metrics + template + "estimate degraded" badge
- Report generation: if Groq fails, use deterministic template with placeholders
- UI shows "waiting for Groq..." status during retries

### Resilience rules

- Short exponential retry on 429 / 5xx
- Deep-dive fallback template + disclaimer
- Never show € without visible assumptions
- CLI entrypoint exists **before** UI (construction order)

### Construction order (implementation)

1. LangGraph CLI with prints (no UI)  
2. CrewAI inside `deep_dive` (testable in isolation)  
3. Checkpointer + `interrupt` / `Command(resume=...)`  
4. Streamlit UI  
5. Two presets (Lumea, SaaS)  

---

## 9. Testing strategy

### Test pyramid

| Layer | What |
| --- | --- |
| Unit | Scoring formulas vs Lumea fixture expected hours/€/rank |
| Unit | Conditional edge selects top 3 only |
| Unit | Assumptions validation (hourly_rate > 0, weeks_per_month > 0) |
| Unit | Pydantic model validation for all domain entities |
| Integration | Graph CLI with mocked LLM: ingest → … → report |
| Integration | Checkpointer resume after interrupt |
| Integration | CrewAI deep-dive with mocked Groq response |
| Fixtures | `profiles/lumea.json`, `profiles/saas.json` |
| E2E | Full Streamlit flow with test user (optional, v1.1) |

### Unit tests (pytest)

- `tests/domain/test_scoring.py` — formula accuracy, edge cases (zero volume, high repetitiveness)
- `tests/domain/test_models.py` — Pydantic validation, serialization
- `tests/graph/test_edges.py` — conditional logic (top-3 selection, check_data loops)
- `tests/llm/test_client.py` — retry logic, fallback template invocation

### Integration tests

- `tests/graph/test_full_flow.py` — mock Groq, run graph end-to-end, verify state transitions
- `tests/crew/test_deep_dive.py` — mock LLM responses, verify crew output structure
- `tests/db/test_repositories.py` — CRUD operations, SQLite→Postgres type compatibility

### Fixtures

- `tests/fixtures/lumea.json` — complete Lumea profile with expected scored output
- `tests/fixtures/saas.json` — SaaS profile with expected scored output
- `tests/fixtures/assumptions.json` — standard assumption sets for regression testing

### Test coverage goal

- Domain layer: 90%+ (scoring, models)
- Graph layer: 70%+ (edges, state transitions)
- CrewAI layer: 50%+ (agent orchestration, output structure)
- UI layer: manual only in v1 (Streamlit tests are flaky)

### Eval suite (v1.1)

Eval suite measuring agent error rates on known cases = **v1.1** (called out so the product still plans for it without blocking v1).

Planned v1.1 eval:
- Ground truth task mappings for 10 real brand operations
- Measure LLM accuracy on `map_tasks` (structure extraction)
- Measure deep-dive quality rubric (tool relevance, risk identification, pilot plan feasibility)

---

## 10. Profiles & presets

### Lumea profile (D2C cosmetics)

`profiles/lumea.json`:
- Brand name: Lumea
- Sector: D2C cosmetics
- Team size: ~12 people
- Channels: Instagram, Shopify, email support
- Sample tasks (free text for `map_tasks` test):
  - "Instagram DM responses: ~50/day, 2 min each, highly repetitive"
  - "Shopify order processing: ~100/day, 3 min each, medium repetitive"
  - "Email support tickets: ~20/day, 10 min each, low repetitive"
  - "Product photography planning: weekly, 60 min, low repetitive"
- Expected assumptions: hourly_rate_eur=35, weeks_per_month=4.33

### SaaS profile

`profiles/saas.json`:
- Brand name: Generic SaaS
- Sector: B2B SaaS
- Team size: ~15 people
- Channels: Intercom, Slack, email, documentation
- Sample tasks:
  - "Onboarding calls: 10/week, 30 min each, medium repetitive"
  - "Churn outreach emails: 50/week, 5 min each, highly repetitive"
  - "Documentation updates: weekly, 2 hours, low repetitive"
  - "Feature request triage: 30/week, 10 min each, medium repetitive"
- Expected assumptions: hourly_rate_eur=45, weeks_per_month=4.33

### Profile structure

JSON schema:
```json
{
  "name": "Brand Name",
  "sector": "D2C|SaaS|Agency|Other",
  "team_size": 12,
  "channels": ["Instagram", "Shopify", "Email"],
  "notes": "Free-text context",
  "tasks": [
    {
      "name": "Task name",
      "volume_per_week": 50,
      "minutes_per_unit": 2,
      "repetitiveness": 5,
      "automatability": 4
    }
  ],
  "default_assumptions": {
    "hourly_rate_eur": 35,
    "weeks_per_month": 4.33,
    "locale": "fr"
  }
}
```

Profiles can be loaded directly (structured tasks) or as free text for `map_tasks` testing.

---

## 11. Interview demo arc (product constraint, not UI chrome)

~6 minutes: problem → Lumea input → live analysis / crew → human checkpoint (edit rate, approve) → final report → trade-offs (cost/run, eval, governance).

Product rule to preserve in copy and behavior: **the agent never alone finalizes figures that commit budget** — human review is mandatory.

---

## 11. Open implementation notes

- Exact LangGraph / CrewAI API names drift; verify current docs at code time (`interrupt`, checkpointer, `Command(resume=...)`, Crew sequential process).
- Prefer pinning Groq model in config for demo stability.
- Password hashing: bcrypt or argon2; never store plaintext.
- i18n: simple dict/catalog for UI strings + report section templates; agent prompts switch by `locale`.

---

## 12. Open implementation notes

- Exact LangGraph / CrewAI API names drift; verify current docs at code time (`interrupt`, checkpointer, `Command(resume=...)`, Crew sequential process).
- Prefer pinning Groq model in config for demo stability.
- Password hashing: bcrypt or argon2; never store plaintext.
- i18n: simple dict/catalog for UI strings + report section templates; agent prompts switch by `locale`.
- Streamlit session state quirks: test that thread ID persists across reruns, especially after human review resume.
- SQLite checkpointer: verify that `SqliteSaver` from LangGraph works with the same DB file as app tables.
- CrewAI Groq integration: check current CrewAI docs for Groq provider setup (may need custom LLM class).

---

## 13. Dependencies & versions

### Core

- Python 3.11+
- Streamlit (latest stable)
- LangGraph (latest stable)
- LangChain (latest stable)
- CrewAI (latest stable)
- SQLAlchemy (latest stable)
- Pydantic v2 (latest stable)

### LLM

- Groq SDK (`groq` package)
- Optional: OpenAI SDK (for local testing with different models)

### Auth & security

- `bcrypt` (password hashing, direct - no passlib)

### Development

- pytest (testing)
- pytest-asyncio (async graph tests)
- python-dotenv (config)

### Installation

`requirements.txt` with pinned versions for demo stability; `requirements-dev.txt` for test tools.

---

## 14. Deployment considerations (v1)

### Local/dev

- Single command: `streamlit run ui/app.py`
- SQLite file created automatically if missing
- `.env` required for `GROQ_API_KEY`

### Production (mono-team)

- Streamlit Cloud or simple VPS deploy
- Environment variables for secrets
- SQLite backup strategy (simple file copy)
- No need for container orchestration in v1

### Data migration path

- Schema designed with portable types (INTEGER, TEXT, JSON)
- SQLAlchemy ORM enables easy switch to Postgres
- Migration tool: Alembic (add in v1.1 if multi-tenant needed)

---

## 15. Approval record

- Approach: **LangGraph-first hybrid** (CrewAI only in deep-dive), with deterministic scoring and Groq fallback
- Architecture §1–§4 reviewed and approved by product owner in design session (2026-08-01)
- Full spec (sections 1–15) completed and locked for implementation planning (2026-08-02)
