# syntax=docker/dockerfile:1
# ── Build stage: install dependencies with uv ───────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache -r pyproject.toml

COPY src/ src/
RUN uv pip install --python /opt/venv/bin/python --no-cache --no-deps .

# ── Runtime stage: slim image with the venv + source ────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIR=/app/frontend

COPY frontend/ frontend/

RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:%s/health" % os.getenv("PORT", "8000"), timeout=3)' || exit 1

CMD ["python", "-m", "ops_copilot"]
