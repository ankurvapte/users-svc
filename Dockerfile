# ---------- Stage 1: build dependencies ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---------- Stage 2: minimal runtime image ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME=users-svc \
    DATA_FILE=/app/data/users.json \
    LOG_LEVEL=INFO \
    PORT=8080

# Run as a non-root user (pillar 7)
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app app ./app
# Seed data: loaded into an empty Postgres table via SEED_FILE, or used
# directly by the JSON adapter when DATABASE_URL is not set.
COPY --chown=app:app data ./data

USER app
EXPOSE 8080

# Docker-level health check; Kubernetes uses its own probes instead.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/ready').status==200 else 1)"

# exec form so uvicorn is PID 1 and receives SIGTERM for graceful shutdown
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
