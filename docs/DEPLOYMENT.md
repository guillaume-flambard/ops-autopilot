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

1. Push the repo to GitHub.
2. In Streamlit Cloud, create an app pointing at `ui/app.py`.
3. Set the secrets in the app's dashboard:
   - `GROQ_API_KEY` (live LLM) and `LLM_PROVIDER=groq`
   - `APP_SECRET` (long random value; used for session hardening)
   - `DEFAULT_LOCALE=fr` (or `en`)
4. **Persistent storage**: Streamlit Cloud instances are ephemeral, so keep
   the SQLite files on attached persistent storage (Streamlit Cloud supports
   persistent disk mounts for paying plans) and point `DATABASE_URL` and
   `CHECKPOINT_DB` at that volume.

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
