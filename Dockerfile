# Ops Autopilot — container image.
#
# Pins the Python runtime (3.12) so the app no longer depends on whatever
# version a host happens to provide. This is what makes the deployment robust:
# the CrewAI dependency tree (and psycopg) has wheels for 3.12, so the boot
# crash seen on Streamlit Community Cloud's Python 3.14 cannot recur here.
#
# Runs on any container host (Render, Railway, Fly.io, a VPS): the app binds to
# 0.0.0.0 on $PORT (defaulting to 8501). Pair it with a persistent volume or a
# Postgres DATABASE_URL for durable accounts/history.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so the layer is cached across code changes.
# build-essential is installed only for the pip step (in case a dependency has
# no wheel for 3.12) and purged in the same layer to keep the image slim.
COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install --upgrade pip \
    && pip install -r requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy the application source.
COPY . .

# Streamlit's default port; hosts that inject $PORT override it at runtime.
EXPOSE 8501

# Shell form so ${PORT} is expanded by the shell at container start.
CMD streamlit run ui/app.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true
