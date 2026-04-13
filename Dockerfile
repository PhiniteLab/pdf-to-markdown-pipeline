# ── Stage 1: base with system deps ──────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: dependencies ───────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml requirements.txt ./
COPY scripts/__init__.py scripts/py.typed scripts/
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: application ────────────────────────────────────────────────────
FROM deps AS app

COPY . .
RUN pip install --no-cache-dir --no-deps .

# Default command: run the full pipeline
ENTRYPOINT ["pdf-pipeline"]
