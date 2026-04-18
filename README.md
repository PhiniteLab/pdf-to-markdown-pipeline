# CortexMark

[![CI](https://github.com/PhiniteLab/pdf-to-markdown-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/PhiniteLab/pdf-to-markdown-pipeline/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/PhiniteLab/pdf-to-markdown-pipeline/graph/badge.svg)](https://codecov.io/gh/PhiniteLab/pdf-to-markdown-pipeline)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A multi-stage pipeline that converts PDF documents into structured Markdown, cleans the output, and splits it into chunks. It runs on CPU and does not require an LLM or any cloud service.

## Features

- **Dual-engine conversion**: combines Docling for structure analysis and markitdown for raw text recovery
- **Multi-stage processing**: PDF → raw Markdown → cleaned Markdown → chunks
- **Idempotent execution**: unchanged files are skipped through a SHA-256 manifest
- **Parallel processing**: thread/process pool support for multi-file workloads
- **Quality assurance**: QA pipeline with GOLD/SILVER/BRONZE/FAIL badges, OCR quality grading (A–F), formula fidelity scoring
- **Scholarly metadata**: extraction of title, authors, abstract, keywords, DOI, and more with BibTeX and APA7 output
- **Citation analysis**: author-year and numeric citation detection, citation graph, Graphviz DOT export
- **Document classification**: automatic detection of paper, textbook, syllabus, slides, report, or generic types
- **Topic classification**: keyword-frequency scoring across RL, ML, NLP, CV, optimization, statistics, math, physics, economics
- **RAG export**: JSONL/JSON output with SHA-256 IDs, token estimates, and chapter/section metadata
- **Multi-format output**: HTML (standalone pages), plain text, YAML with front-matter
- **GitHub Pages generation**: static site with document cards, navigation, and breadcrumbs
- **Figure extraction**: image catalog from Markdown and HTML `<img>` references with file existence validation
- **Version diffing**: unified diff format with JSON change statistics across file trees
- **Plugin architecture**: custom pipeline hooks (`pre_convert`, `post_convert`, `pre_clean`, `post_clean`, `pre_chunk`, `post_chunk`, `post_pipeline`) via file-based discovery
- **Template rendering**: deterministic source profile and section template population
- **Docker support**: containerized execution with minimal setup
- **VS Code extension**: session management, Markdown preview panel, quality dashboard, analysis module integration, progress visualization, and a chat-oriented control surface
- **Validated by an extensive pytest suite** with a minimum coverage threshold of 70%

## Dual-Engine Approach

| Engine | Strengths | Weaknesses |
|--------|-----------|------------|
| **docling** | Structural analysis for headings, formulas, and algorithmic blocks | May skip some paragraphs |
| **markitdown** | Extracts more raw text in difficult PDFs | Can turn formulas into table-like artifacts |

The default mode, `dual`, uses Docling output as the structural backbone and fills missing paragraphs from markitdown output through fingerprint matching. Table artifacts and short fragments are filtered automatically.

## Migration from PhiniteLab PDF Pipeline

This release rebrands the public package and extension surfaces to **CortexMark**.

| Old surface | New surface |
|---|---|
| PyPI package `phinitelab-pdf-pipeline` | PyPI package `cortexmark` |
| Python module `phinitelab_pdf_pipeline` | Python module `cortexmark` |
| CLI command `phinitelab-pdf-pipeline` | CLI command `cortexmark` |
| VS Code extension `phinitelab-pdf-pipeline-vscode` | VS Code extension `cortexmark-vscode` |
| Session store `.phinitelab-pdf-pipeline/` | Session store `.cortexmark/` |

Notes:
- This is a **breaking rename** for public package, module, CLI, and extension IDs.
- The VS Code extension now uses a new extension identity; existing users should install the new `cortexmark-vscode` package manually.
- Existing workspace session data is read from the legacy `.phinitelab-pdf-pipeline/sessions.json` path and copied into `.cortexmark/sessions.json` automatically when needed.


## Installation

### Recommended installation paths

Choose the smallest installation that matches your workload.

| Scenario | Command | What you get |
|---|---|---|
| Lightweight CPU setup | `pip install cortexmark` | Installs the CLI plus the `markitdown` engine |
| Layout-aware CPU setup | `pip install "cortexmark[docling]"` | Adds Docling for `docling` and `dual` modes |
| GPU-oriented setup | `pip install "cortexmark[gpu]"` | Same Docling-enabled workflow, intended for CUDA-capable hosts |
| Developer setup | `pip install -e ".[dev]"` | Runtime + tests + lint/type/build tooling |
| Docs build setup | `pip install -e ".[docs]"` | MkDocs + mkdocstrings for local docs builds |

### Requirements and dependency matrix

| Item | Needed for | Required? | Notes |
|---|---|---|---|
| Python 3.11+ | All installs | Yes | Supported baseline runtime |
| `cortexmark` package | CLI + modules | Yes | Provides the `cortexmark` command |
| `markitdown[pdf]` | `markitdown` engine and `dual` gap-fill | Installed by default | Lightweight CPU-friendly path |
| `docling` | `docling` engine and `dual` structural parsing | Optional | Install via `cortexmark[docling]` or `cortexmark[gpu]` |
| PyTorch | Docling runtime | Optional | Pre-install CPU PyTorch on CPU-only hosts to avoid large CUDA downloads |
| Poppler | Some PDF/OCR-adjacent workflows | Optional | Helpful, not mandatory for every document |
| Tesseract OCR | Scanned/image-heavy PDFs and OCR-style workflows | Optional | Only useful when OCR is needed |
| Docker | Containerized execution | Optional | Good for reproducible setups |

> CortexMark does **not** require an API key, LLM, or cloud service for its core pipeline.

### Install with pip

```bash
pip install cortexmark
```

This installs the lightweight default runtime declared in `pyproject.toml` and is enough for:

- `cortexmark --engine markitdown`
- Markdown cleaning, chunking, export, quality reports, and downstream analysis on produced Markdown

### Install with Docling on CPU

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

Use this when you want:

- `--engine docling`
- `--engine dual`
- stronger layout recovery for complex academic PDFs

### Install with GPU support

```bash
pip install "cortexmark[gpu]"
```

Or preinstall a specific CUDA-targeted PyTorch build first, then install the extra.

### System tools

Optional system tools:

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

These tools are **not mandatory for every installation**. They become useful when:

- your PDFs are scanned or image-heavy,
- your environment doctor asks for them,
- or your preferred PDF workflow depends on them.

### Developer installation

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

For local documentation builds:

```bash
pip install -e ".[docs]"
```

## What CortexMark processes

### Primary input types

The full pipeline starts from **PDF files**:

- a single `.pdf`
- or a directory tree containing `.pdf` files

Examples:

```bash
cortexmark --input path/to/paper.pdf
cortexmark --input path/to/folder-of-pdfs
```

### Downstream module input types

After conversion, most modules work on **Markdown files** produced by the pipeline.

| Input type | Used by |
|---|---|
| `.pdf` | `convert`, full `cortexmark` pipeline entrypoint |
| `.md` trees | `clean`, `chunk`, `metadata`, `citations`, `doc_type`, `topics`, `figures`, `rag_export`, `semantic_chunk`, `cross_ref`, `algorithm_extract`, `notation_glossary`, `formula_validate`, `citation_context`, `scientific_qa`, `multi_format`, `ghpages` |
| `outline` / `syllabus` `.md` or `.txt` helper files | `render_templates` |

### Best-fit document categories

CortexMark is optimized for:

- academic papers
- lecture notes
- textbooks and book chapters
- theses and reports
- math/theorem-heavy PDFs
- algorithm/code-heavy technical documents
- scanned or noisy PDFs where a fallback recovery path helps

## Outputs you will get

By default, CortexMark writes under `outputs/`.

| Output | Typical path | Description |
|---|---|---|
| Raw Markdown | `outputs/raw_md/` | First-pass PDF → Markdown conversion |
| Cleaned Markdown | `outputs/cleaned_md/` | Normalized Markdown with repeated noise reduced |
| Chunks | `outputs/chunks/` | Section-based chunk files such as `chunk_001_Introduction.md` |
| Semantic chunks | `outputs/semantic_chunks/` | Theorem/proof/definition-aware chunk artifacts |
| Quality reports | `outputs/quality/` | QA, citation, formula, cross-ref, notation, and scientific validation reports |
| Rendered templates | render-specific folders | Source profile and section/task templates |
| RAG exports | quality/export locations | JSON / JSONL records with chunk IDs and scholarly metadata |
| Static site exports | GitHub Pages / HTML outputs | HTML pages for browsing processed content |

With `--session-name`, all of the above are isolated under `sessions/<session-name>/...`.

## Basic usage

> **Important:** the published `cortexmark` package ships the CLI and Python modules, but it does **not** ship the repository's example `configs/pipeline.yaml`.
>
> If you are working from a cloned repository, you can use the checked-in `configs/pipeline.yaml`.
> If you installed from PyPI into a fresh working directory, create your own config file first as shown in `docs/getting-started/quickstart.md`.

### CLI command

After installation, use the `cortexmark` command:

```bash
# Run the default pipeline
cortexmark

# Use a specific file or directory
cortexmark --input path/to/paper.pdf
cortexmark --input path/to/folder-of-pdfs

# Choose a conversion engine
cortexmark --engine markitdown
cortexmark --engine docling
cortexmark --engine dual

# Run only selected stages
cortexmark --stages convert clean
cortexmark --stages analyze validate

# Isolate outputs inside a named session workspace
cortexmark --session-name experiment-1
```

Run `cortexmark --help` to view all arguments.

### Makefile shortcuts

```bash
make help                # List available commands
make all                 # Run convert → clean → chunk → render
make analyze             # Run semantic/cross-ref/algorithm/notation modules
make validate            # Run formula/scientific QA/citation validation modules
make benchmark-reference # Run the reference benchmark gate
make test                # Run pytest
make lint                # Run Ruff checks
```

### Run modules directly

```bash
python -m cortexmark.convert --input data/raw/paper.pdf --engine docling
python -m cortexmark.clean --input outputs/raw_md --output-dir outputs/cleaned_md
python -m cortexmark.chunk --input outputs/cleaned_md --output-dir outputs/chunks
python -m cortexmark.cross_ref --input outputs/cleaned_md
python -m cortexmark.rag_export --input outputs/chunks
python -m cortexmark.reference_eval --benchmarks benchmarks/references --baseline benchmarks/references/baseline.json
```

## Pipeline stages

```text
PDF files
   │
   ▼
┌──────────┐   raw_md/    ┌───────┐  cleaned_md/  ┌───────┐  chunks/
│ convert  │ ───────────► │ clean │ ────────────► │ chunk │ ──────────► output
│ (engine) │              │       │               │       │
└──────────┘              └───────┘               └───────┘
                                                       │
                                                       ▼
                                               ┌───────────────┐
                                               │    render     │
                                               │  templates    │
                                               └───────────────┘
```

1. **convert** — PDF → raw Markdown using `markitdown`, `docling`, or `dual`
2. **clean** — normalize repeated headers/footers, line wraps, and noisy formatting
3. **chunk** — split cleaned Markdown into logical sections
4. **render** *(optional)* — generate source-profile and section templates
5. **analyze** *(optional)* — semantic chunking, cross-reference analysis, algorithm extraction, notation glossary
6. **validate** *(optional)* — formula validation, citation context extraction, scientific QA

### VS Code extension

The published VS Code extension is **`PhiniteLab.cortexmark-vscode`**.

Install it from the VS Code Extensions view by searching for **CortexMark**, then:

1. install the extension,
2. install the Python backend separately with `pip install cortexmark` (or `cortexmark[docling]`),
3. open your workspace,
4. run **CortexMark: Environment Doctor**,
5. create a session and add PDFs.

The extension documentation lives in:

- `vscode-extension/README.md`
- `docs/vscode/setup.md`
- `docs/vscode/commands.md`

## Portable path and environment configuration

CortexMark resolves runtime paths with a stable precedence order:

1. CLI arguments
2. environment variables
3. workspace or project `.env`
4. `configs/pipeline.yaml`
5. repo-relative defaults

Useful overrides include `PROJECT_ROOT`, `DATA_DIR`, `OUTPUT_DIR`, `REPORT_DIR`, `LOG_DIR`, `CHECKPOINT_DIR`, `CACHE_DIR`, `MODEL_DIR`, `EXTERNAL_BIN_DIR`, plus direct output overrides such as `RAW_DATA_DIR`, `OUTPUT_RAW_MD`, `OUTPUT_CLEANED_MD`, `OUTPUT_CHUNKS`, `OUTPUT_SEMANTIC_CHUNKS`, and `MANIFEST_FILE`.

A ready-to-copy template is available in [`.env.example`](.env.example).

## Docker

For a containerized workflow:

```bash
docker compose up pipeline
docker compose --profile test up
```

This is useful when you want a reproducible local environment or do not want to manage host dependencies manually.

## Configuration

All settings are controlled from `configs/pipeline.yaml`:

```yaml
source_id: default

paths:
  data_raw: data/raw
  output_raw_md: outputs/raw_md
  output_cleaned_md: outputs/cleaned_md
  output_chunks: outputs/chunks
  output_quality: outputs/quality
  output_semantic_chunks: outputs/semantic_chunks

convert:
  engine: dual                         # docling | markitdown | dual
  docling:
    device: auto                       # auto | cpu | cuda
    num_threads: 1
    do_ocr: false
    do_table_structure: true
    table_structure_mode: accurate     # accurate | fast
  markitdown:
    enabled: true

clean:
  min_repeated_header_count: 3
  max_repeated_header_length: 80

chunk:
  split_levels: [1, 2]                 # Heading levels that trigger new chunks

render_templates:
  outline_file: 00_meta/outline.md
  language: en
  max_summary_chars: 240
  max_scope_items: 6
  max_tasks: 5

logging:
  level: INFO                          # DEBUG | INFO | WARNING | ERROR
  format: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
  date_format: "%Y-%m-%d %H:%M:%S"

idempotency:
  enabled: true
  manifest_file: outputs/.manifest.json
```

Any script can receive an alternative config file through `--config <path>`.

## Project Structure

```text
pdf-to-markdown-pipeline/
├── cortexmark/           # Python package
│   ├── run_pipeline.py                #   Orchestrator and CLI entry point
│   ├── convert.py                     #   PDF → Markdown (docling/markitdown/dual)
│   ├── clean.py                       #   Markdown cleanup and normalization
│   ├── chunk.py                       #   Split by heading levels into numbered chunks
│   ├── common.py                      #   Config, logging, manifest, path utilities
│   ├── render_templates.py            #   Deterministic template rendering
│   ├── parallel.py                    #   Thread/process pool helpers
│   ├── plugin.py                      #   Plugin base class and registry
│   ├── qa_pipeline.py                 #   Quality checks and badge scoring
│   ├── ocr_quality.py                 #   OCR text quality metrics (A–F grade)
│   ├── formula_score.py               #   Formula/equation fidelity scoring
│   ├── metadata.py                    #   Scholarly metadata (BibTeX, APA7, YAML)
│   ├── citations.py                   #   Citation graph extraction (DOT, JSON)
│   ├── doc_type.py                    #   Document type detection with templates
│   ├── topics.py                      #   Topic classification by keyword frequency
│   ├── figures.py                     #   Figure reference catalog
│   ├── diff.py                        #   Version-to-version diff reporting
│   ├── rag_export.py                  #   RAG-oriented JSONL/JSON export
│   ├── semantic_chunk.py              #   Scientific-aware chunking (theorem/proof/def/algo)
│   ├── cross_ref.py                   #   Cross-reference resolution and linking
│   ├── algorithm_extract.py           #   Algorithm/pseudocode extraction and analysis
│   ├── notation_glossary.py           #   Mathematical notation glossary builder
│   ├── formula_validate.py            #   Enhanced LaTeX formula validation
│   ├── citation_context.py            #   Citation context extraction and classification
│   ├── scientific_qa.py               #   Scientific document quality assurance checks
│   ├── multi_format.py                #   HTML / plain text / YAML export
│   └── ghpages.py                     #   GitHub Pages static site generation
├── configs/
│   └── pipeline.yaml                  # Central configuration file
├── tests/
│   └── test_pipeline_structure.py     # Extensive pytest suite (70% minimum coverage)
├── data/raw/                          # Source PDF files (user-provided)
│   ├── books/
│   ├── notes/
│   ├── manuscripts/
│   ├── reports/
│   ├── textbooks/chapters/
│   └── theses/
├── outputs/                           # Generated outputs
│   ├── raw_md/                        #   Raw Markdown from conversion
│   ├── cleaned_md/                    #   Cleaned and normalized Markdown
│   └── chunks/                        #   Chunked output sections
├── vscode-extension/                  # VS Code extension v0.3.3 (TypeScript)
│   ├── src/extension.ts               #   Activation, command registration, file watchers
│   ├── src/sessionManager.ts          #   Session persistence and events
│   ├── src/sessionTree.ts             #   Tree data provider (Sessions, Actions, Analysis, Outputs)
│   ├── src/pipelineRunner.ts          #   Subprocess spawning with progress bar & cancellation
│   ├── src/previewPanel.ts            #   Markdown preview WebView with QA badges & math
│   ├── src/dashboardPanel.ts          #   Quality metrics dashboard WebView
│   ├── src/chatView.ts                #   Chat panel with command-driven workflows
│   └── src/types.ts                   #   TypeScript interfaces
├── .github/workflows/ci.yml          # GitHub Actions CI (lint + test + typecheck)
├── pyproject.toml                     # Package metadata, dependencies, tool config
├── Makefile                           # Common developer commands
├── Dockerfile                         # Multi-stage container image
├── docker-compose.yml                 # Pipeline, test, and lint services
└── requirements.txt                   # Pinned runtime dependencies
```

## Troubleshooting

| Problem | Resolution |
|---------|------------|
| `ImportError: The 'docling' package is required` | Docling is not included in the default installation. Install it with `pip install "cortexmark[docling]"` or `pip install "cortexmark[gpu]"`. |
| `ModuleNotFoundError: No module named 'cortexmark'` | Make sure the project was installed with `pip install -e .`. Prefer `python -m cortexmark.convert` over `python cortexmark/convert.py`. |
| `FileNotFoundError: Config file not found` | Pass a valid config path with `--config`, for example `cortexmark --config configs/pipeline.yaml`. |
| Docling installation fails | Docling may require system libraries and a compiler toolchain. On Debian/Ubuntu, install `build-essential` and `poppler-utils`, or use Docker instead. |
| Memory issues on large PDFs | Verify `num_threads: 1` and `device: cpu` in `configs/pipeline.yaml`. If needed, constrain Docker resources explicitly. |
| Formulas look corrupted | `engine: dual` usually gives the best output. Compare with `--engine docling` and `--engine markitdown` when debugging. |
| Idempotency does not skip unchanged files | Check that `outputs/.manifest.json` is writable. To rebuild from scratch, run `make clean-outputs`. |
| Tests fail after code changes | Run `make lint && make test && pyright cortexmark/` to check all quality gates. |

## Development Notes

### Tests

```bash
make test                          # or: python -m pytest tests/ -v
```

### Linting and formatting

```bash
make lint                          # Checks only
make format                        # Apply automatic fixes
```

### Type checking

```bash
pyright cortexmark/   # standard mode, currently 0 errors, 0 warnings
```

### Coverage

```bash
python -m pytest tests/ --cov=cortexmark --cov-report=term-missing
```

The minimum coverage threshold is 70%, enforced by pytest-cov.

### Pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

### Build

```bash
pip install build
python -m build                    # creates .tar.gz and .whl files under dist/
```

## License

This project is licensed under the [MIT License](LICENSE).
