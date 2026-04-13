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
COPY phinitelab_pdf_pipeline/__init__.py phinitelab_pdf_pipeline/py.typed phinitelab_pdf_pipeline/
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: application ────────────────────────────────────────────────────
FROM deps AS app

RUN groupadd --gid 1000 pipeline && \
    useradd --uid 1000 --gid pipeline --create-home pipeline

COPY . .
RUN pip install --no-cache-dir --no-deps .

USER pipeline

HEALTHCHECK --interval=30s --timeout=5s --retries=2 \
    CMD ["python", "-c", "import phinitelab_pdf_pipeline; print('ok')"]

ENTRYPOINT ["phinitelab-pdf-pipeline"]
