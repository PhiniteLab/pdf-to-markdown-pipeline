# Installation

This page explains:

1. how to install CortexMark,
2. which dependencies are optional,
3. which tools are actually used at runtime.

## Quick recommendation

If you are starting fresh, install the lightweight package first:

```bash
pip install cortexmark
```

That gives you:

- the `cortexmark` CLI,
- the default `markitdown` conversion path,
- the rest of the Markdown cleaning / chunking / analysis / export pipeline.

If you later need stronger layout-aware PDF parsing, move to the Docling-enabled install.

## Installation matrix

| Scenario | Command | Best for |
|---|---|---|
| Lightweight CPU install | `pip install cortexmark` | First-time users, simple PDFs, CPU-only hosts |
| Layout-aware CPU install | `pip install "cortexmark[docling]"` | Complex academic PDFs, equations, stronger structure recovery |
| GPU-oriented install | `pip install "cortexmark[gpu]"` | CUDA-capable systems using Docling workloads |
| Developer install | `pip install -e ".[dev]"` | Local development, testing, linting, packaging |
| Docs build install | `pip install -e ".[docs]"` | Building the MkDocs site locally |

## Core requirements

- **Python 3.11+**
- `pip`
- local PDF files to process

CortexMark does **not** require:

- an LLM,
- an API key,
- a cloud service.

## Optional components

| Component | When you need it | Required? |
|---|---|---|
| `docling` | `docling` / `dual` engine workflows | Optional |
| PyTorch | Docling runtime | Optional |
| Poppler | Some PDF and OCR-adjacent environments | Optional |
| Tesseract OCR | Scanned or image-heavy PDFs | Optional |
| Docker | Containerized workflow | Optional |
| VS Code | Extension-based UI workflow | Optional |

## Recommended install commands

### 1) Lightweight install

```bash
pip install cortexmark
```

Default runtime dependencies include:

- `markitdown[pdf]`
- `PyYAML`

This is enough for:

- `--engine markitdown`
- downstream Markdown analysis/export modules

### 2) Docling on CPU

On CPU-only systems, preinstall CPU PyTorch first:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

This is the recommended setup for:

- `--engine docling`
- `--engine dual`
- layout-aware academic PDFs

### 3) GPU-oriented install

```bash
pip install "cortexmark[gpu]"
```

If you need a specific CUDA build, preinstall the matching PyTorch variant first.

## Optional system packages

Install these only when your environment or documents benefit from them.

=== "Ubuntu / Debian"

    ```bash
    sudo apt-get update
    sudo apt-get install -y poppler-utils tesseract-ocr
    ```

=== "macOS"

    ```bash
    brew install poppler tesseract
    ```

=== "Windows (WSL)"

    ```bash
    sudo apt-get update
    sudo apt-get install -y poppler-utils tesseract-ocr
    ```

Use them when:

- your PDFs are scanned or image-heavy,
- you rely on OCR-oriented workflows,
- or environment diagnostics specifically ask for them.

## Developer installation

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional docs tooling:

```bash
pip install -e ".[docs]"
```

## What gets used at runtime?

| Tool / package | What CortexMark does with it |
|---|---|
| `cortexmark` | Installs the package and CLI |
| `markitdown[pdf]` | Runs PDF extraction in `markitdown` mode and supports text recovery in `dual` mode |
| `docling` | Runs layout-aware PDF parsing in `docling` mode and structural parsing in `dual` mode |
| `PyYAML` | Loads `configs/pipeline.yaml` |
| PyTorch | Supports Docling execution |
| Poppler / Tesseract | Only used when document/environment needs them |

## Next steps

- Continue to **[Quick Start](quickstart.md)**
- Review **[Requirements, Inputs, and Outputs](../guide/inputs-and-outputs.md)**
- If you prefer an editor workflow, see **[VS Code Setup](../vscode/setup.md)**
