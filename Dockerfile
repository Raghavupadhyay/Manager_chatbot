# syntax=docker/dockerfile:1
# ── Build stage: install dependencies with uv ───────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache -r pyproject.toml

# ── Runtime stage: slim image with the venv + source ────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY frontend/ frontend/
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "-m", "ops_copilot"]
