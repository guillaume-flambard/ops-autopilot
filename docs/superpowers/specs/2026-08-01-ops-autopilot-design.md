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

---

## 8. LLM, errors, config

### Config (`.env`)

- `GROQ_API_KEY` (required for live LLM paths)
- `APP_SECRET` (session / password hashing pepper)
- `DATABASE_URL` (default `sqlite:///./ops_autopilot.db`)
- `DEFAULT_LOCALE` (`fr` or `en`)
- Optional: `GROQ_MODEL` (pin a supported Groq model id)

### Resilience

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

## 9. Testing

| Layer | What |
| --- | --- |
| Unit | Scoring formulas vs Lumea fixture expected hours/€/rank |
| Unit | Conditional edge selects top 3 only |
| Integration | Graph CLI with mocked LLM: ingest → … → report |
| Fixtures | `profiles/lumea.json`, `profiles/saas.json` |

Eval suite measuring agent error rates on known cases = **v1.1** (called out so the product still plans for it without blocking v1).

---

## 10. Interview demo arc (product constraint, not UI chrome)

~6 minutes: problem → Lumea input → live analysis / crew → human checkpoint (edit rate, approve) → final report → trade-offs (cost/run, eval, governance).

Product rule to preserve in copy and behavior: **the agent never alone finalizes figures that commit budget** — human review is mandatory.

---

## 11. Open implementation notes

- Exact LangGraph / CrewAI API names drift; verify current docs at code time (`interrupt`, checkpointer, `Command(resume=...)`, Crew sequential process).
- Prefer pinning Groq model in config for demo stability.
- Password hashing: bcrypt or argon2; never store plaintext.
- i18n: simple dict/catalog for UI strings + report section templates; agent prompts switch by `locale`.

---

## 12. Approval record

- Approach: **LangGraph-first hybrid** (CrewAI only in deep-dive), with deterministic scoring and Groq fallback  
- Architecture §1–§4 reviewed and approved by product owner in design session (2026-08-01)
)
