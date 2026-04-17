# Installation

## Requirements

- Python 3.11 or later
- `poppler-utils` and `tesseract-ocr` (for PDF extraction)

Install system dependencies:

=== "Ubuntu / Debian"

    ```bash
    sudo apt-get update && sudo apt-get install -y poppler-utils tesseract-ocr
    ```

=== "macOS"

    ```bash
    brew install poppler tesseract
    ```

=== "Windows (WSL)"

    ```bash
    sudo apt-get update && sudo apt-get install -y poppler-utils tesseract-ocr
    ```

## Install with pip (lightweight, CPU-only)

```bash
pip install -e .
```

This installs the MarkItDown engine only.

## Install with Docling engine (CPU)

```bash
pip install -e ".[docling]"
```

Docling provides deep layout analysis with better accuracy for complex PDFs.

## Install with GPU support

```bash
pip install -e ".[gpu]"
```

Requires CUDA-compatible GPU and `torch` with CUDA.

## Which installation should I choose?

| Setup | Best for | Size |
|-------|----------|------|
| `pip install -e .` | Quick testing, simple PDFs | ~50 MB |
| `pip install -e ".[docling]"` | Production, complex layouts | ~2 GB |
| `pip install -e ".[gpu]"` | Large batches, GPU available | ~4 GB |

## Developer installation

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pre-commit install --hook-type commit-msg
```

## Portable path overrides

CortexMark can be relocated to another user account, machine, workspace path, CI runner, or container without code edits.
Use CLI arguments first, then environment variables or a `.env` file, and fall back to `configs/pipeline.yaml` only when you want a checked-in project default.

Common overrides:

```bash
cp .env.example .env
# edit values as needed
export OUTPUT_DIR=/tmp/cortexmark-output
export CACHE_DIR=/tmp/cortexmark-cache
```

Useful variables: `PROJECT_ROOT`, `DATA_DIR`, `OUTPUT_DIR`, `REPORT_DIR`, `LOG_DIR`, `CHECKPOINT_DIR`, `CACHE_DIR`, `MODEL_DIR`, `EXTERNAL_BIN_DIR`.

## Docker

```bash
docker build -t pdf-pipeline .
docker run --rm -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" pdf-pipeline
```

See the [Docker guide](../guide/docker.md) for details.
