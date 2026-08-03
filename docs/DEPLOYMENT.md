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
4. **Persistent storage**: Streamlit Cloud instances are ephemeral, so the
   SQLite files (`ops_autopilot.db`, `ops_autopilot_checkpoints.db`) reset on
   redeploy. For persistent history, attach a persistent disk (paying plans)
   and point `DATABASE_URL` and `CHECKPOINT_DB` at that volume. For an
   interview demo, ephemeral storage is fine.

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
