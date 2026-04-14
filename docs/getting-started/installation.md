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

## Docker

```bash
docker build -t pdf-pipeline .
docker run --rm -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" pdf-pipeline
```

See the [Docker guide](../guide/docker.md) for details.
