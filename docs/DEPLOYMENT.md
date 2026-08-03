# Deployment

Design spec section 14: how to run Ops Autopilot in production for a
mono-team (the product's target). v1 deliberately avoids container
orchestration and multi-tenant infrastructure.

## Local / dev

- One command: `make run` (or `streamlit run ui/app.py`).
- `ops_autopilot.db` (app tables) and `ops_autopilot_checkpoints.db`
  (LangGraph checkpointer) are created on first run if missing.
- `.env` needs `GROQ_API_KEY` for live LLM calls; without it the app runs
  in offline mock mode (`LLM_PROVIDER=mock`).

## Production (mono-team)

Two supported paths. Both are single-process Streamlit apps plus a SQLite
file; pick based on where you already host things.

### Option A - Streamlit Cloud

1. Push the repo to GitHub (it is public: `guillaume-flambard/ops-autopilot`).
2. In Streamlit Cloud, create a new app pointing at the repo, branch `main`,
   main file `ui/app.py`.
3. Set the secrets in the app's dashboard (Settings > Secrets, TOML):
   ```toml
   GROQ_API_KEY="your_groq_key"
   GROQ_MODEL="llama-3.3-70b-versatile"
   JINA_API_KEY="your_jina_key"
   APP_SECRET="a_long_random_string"
   DEFAULT_LOCALE="fr"
   LLM_PROVIDER="mock"
   ```
   - `LLM_PROVIDER=mock` is the safe default: Streamlit Cloud has no local
     Ollama, so `ollama` would fall back to mock anyway. With a Groq key the
     UI offers `groq`, which is the recommended provider for site analysis.
   - `JINA_API_KEY` lifts the r.jina.ai rate limit for website analysis.
4. **Persistent storage**: Streamlit Cloud instances are ephemeral and their
   working directory is read-only, so the default SQLite files do not persist
   (the app falls back to a writable temp dir that resets on every redeploy /
   restart — accounts and history are lost). For real persistence, point
   `DATABASE_URL` at a managed Postgres and add it to the secrets:
   ```toml
   DATABASE_URL="postgresql+psycopg://user:pass@host:5432/ops_autopilot"
   ```
   - The `psycopg[binary]` driver is already in `requirements.txt` (it ships
     cp314 wheels, so it installs on the Streamlit Cloud runtime). No app
     changes are needed — every repo function is URL-agnostic and
     `init_db()` creates the tables on first boot.
   - Free managed options: Supabase or Neon. Use the direct/pooled connection
     string they give you, swapping the scheme for `postgresql+psycopg://`.
     Step-by-step walkthrough (provision → connect → verify persistence):
     see [POSTGRES_SETUP.md](POSTGRES_SETUP.md).
   - The LangGraph checkpointer still uses a local (ephemeral) SQLite file for
     in-flight analysis state; that is transient and fine to lose on restart.
   - For an interview demo, the SQLite fallback is fine — just know accounts
     reset when the instance recycles.

### Option B - VPS (single box)

```bash
git clone https://github.com/guillaume-flambard/ops-autopilot.git /opt/ops-autopilot
cd /opt/ops-autopilot
uv venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, APP_SECRET, LLM_PROVIDER=groq
```

Run behind a reverse proxy (Caddy/nginx) with a systemd unit:

```ini
[Unit]
Description=Ops Autopilot (Streamlit)
After=network.target

[Service]
WorkingDirectory=/opt/ops-autopilot
ExecStart=/opt/ops-autopilot/.venv/bin/streamlit run ui/app.py --server.port 8501 --server.address 127.0.0.1
Restart=on-failure
EnvironmentFile=/opt/ops-autopilot/.env

[Install]
WantedBy=multi-user.target
```

Point Caddy at `http://127.0.0.1:8501` with automatic HTTPS.

## SQLite backup strategy

SQLite is a single file, so backup is a safe file copy. For a mono-team app
a daily `cron` + simple retention is enough:

```bash
#!/usr/bin/env bash
# /etc/cron.daily/ops-autopilot-backup
set -eu
DB_DIR=/opt/ops-autopilot/data
BACKUP_DIR=/opt/ops-autopilot/backups
mkdir -p "$BACKUP_DIR"
timestamp=$(date +%F_%H%M)
# sqlite3 .backup is crash-safe (consistent snapshot even while app writes)
sqlite3 "$DB_DIR/ops_autopilot.db" ".backup '$BACKUP_DIR/app-$timestamp.db'"
sqlite3 "$DB_DIR/ops_autopilot_checkpoints.db" ".backup '$BACKUP_DIR/checkpoints-$timestamp.db'"
# keep 14 days
find "$BACKUP_DIR" -name '*.db' -mtime +14 -delete
```

Test restore by opening a backup with `sqlite3 file.db '.tables'` before
trusting it.

## Postgres migration path

The schema is portable by design (`db/models.py` uses only INTEGER, TEXT,
DateTime, String; no SQLite-only types), and every repo function accepts an
explicit `url`, so switching is a configuration change.

1. Install Alembic (planned for v1.1):
   ```bash
   uv pip install alembic
   alembic init migrations
   ```
2. Point `DATABASE_URL` at Postgres, e.g.
   `postgresql+psycopg2://user:pass@host:5432/ops_autopilot`.
3. Two extra concerns on Postgres:
   - the LangGraph checkpointer currently defaults to a local SQLite file
     (`db/repo.py:checkpoint_db_path`); on Postgres point `CHECKPOINT_DB`
     at a writable volume, or move the checkpointer to a Postgres-backed
     saver in a later version;
   - `DateTime(timezone=True)` uses `utcnow` (naive UTC) today - normalize
     to timezone-aware datetimes before multi-tenant use.

Do not attempt a live in-place migration of a SQLite file to Postgres by
copying bytes; export rows via SQL and re-insert.
