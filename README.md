# PDF to Markdown Pipeline

[![CI](https://github.com/PhiniteLab/pdf-to-markdown-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/PhiniteLab/pdf-to-markdown-pipeline/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

This is a multi-stage pipeline that converts PDF documents into structured Markdown, cleans the output, and splits it into chunks. It runs on CPU and does not require an LLM or any cloud service.

## Features

- **Dual-engine conversion**: combines Docling for structure analysis and markitdown for raw text recovery
- **Multi-stage processing**: PDF → raw Markdown → cleaned Markdown → chunks
- **Idempotent execution**: unchanged files are skipped through a SHA-256 manifest
- **Parallel processing**: thread/process pool support for multi-file workloads
- **Quality checks**: automatic validation for OCR quality, formula fidelity, and encoding issues
- **Plugin architecture**: custom pipeline hooks can be added without changing core flow
- **Docker support**: containerized execution with minimal setup
- **Validated by 429 tests** with a minimum coverage threshold of 70%

## Dual-Engine Approach

| Engine | Strengths | Weaknesses |
|--------|-----------|------------|
| **docling** | Structural analysis for headings, formulas, and algorithmic blocks | May skip some paragraphs |
| **markitdown** | Extracts more raw text in difficult PDFs | Can turn formulas into table-like artifacts |

The default mode, `dual`, uses Docling output as the structural backbone and fills missing paragraphs from markitdown output through fingerprint matching. Table artifacts and short fragments are filtered automatically.

## Installation

### Requirements

- Python 3.11 or newer
- Optional: Poppler and Tesseract for OCR and advanced PDF handling

### Install with pip

```bash
pip install git+https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
```

### Developer installation

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the runtime dependencies together with the development toolchain, including pytest, pytest-cov, Ruff, Pyright, and pre-commit.

### Install with Docker

```bash
docker compose up pipeline        # Run the pipeline
docker compose --profile test up  # Run the test profile
```

## Usage

### CLI command

After installation, you can use the `pdf-pipeline` command:

```bash
# Run all stages in order
pdf-pipeline

# Run only selected stages
pdf-pipeline --stages convert clean

# Use a different config file
pdf-pipeline --config configs/pipeline.yaml

# Select a conversion engine
pdf-pipeline --engine docling      # Docling only
pdf-pipeline --engine markitdown   # markitdown only
pdf-pipeline --engine dual         # combined mode (default)
```

Run `pdf-pipeline --help` to view all available arguments.

### Makefile shortcuts

```bash
make help         # List available commands
make all          # Run the full pipeline
make convert      # Run only PDF → Markdown conversion
make clean        # Run only the cleaning stage
make chunk        # Run only chunk generation
make render       # Run only template rendering
make test         # Run the test suite
make lint         # Run Ruff lint and formatting checks
make format       # Apply automatic formatting fixes
```

### Run modules directly

Each module can also be executed independently:

```bash
python -m scripts.convert --config configs/pipeline.yaml
python -m scripts.clean --config configs/pipeline.yaml
python -m scripts.chunk --config configs/pipeline.yaml
python -m scripts.qa_pipeline --input outputs/cleaned_md --output reports/qa.md
```

## Pipeline Stages

```text
PDF files ──► convert ──► clean ──► chunk ──► output
              (dual)     (normalize)  (split)
```

1. **convert**: PDF → raw Markdown. Docling handles structure, while markitdown fills text gaps.
2. **clean**: removes page numbers, repeated headers/footers, and broken line wraps. Heading hierarchy is normalized.
3. **chunk**: splits cleaned Markdown into logical sections based on chapter and section headings.
4. **render** *(optional)*: fills template files deterministically from syllabus and weekly content.

## Configuration

All settings are controlled from `configs/pipeline.yaml`:

```yaml
course_id: mkt4822-RL

paths:
  data_raw: data/raw
  output_raw_md: outputs/raw_md
  output_cleaned_md: outputs/cleaned_md
  output_chunks: outputs/chunks

convert:
  engine: dual                         # docling | markitdown | dual
  docling:
    device: cpu
    num_threads: 1
    do_ocr: false
    do_table_structure: true
    table_structure_mode: accurate     # accurate | fast

clean:
  min_repeated_header_count: 3

chunk:
  split_levels: [1, 2]                 # Heading levels

idempotency:
  enabled: true                        # Skip unchanged files through the SHA-256 manifest

logging:
  level: INFO
```

Any script can receive an alternative config file through `--config <path>`.

## Project Structure

```text
pdf-to-markdown-pipeline/
├── scripts/                   # Python package containing the pipeline modules
│   ├── run_pipeline.py        #   Orchestrator and CLI entry point
│   ├── convert.py             #   PDF → Markdown conversion
│   ├── clean.py               #   Markdown cleanup
│   ├── chunk.py               #   Markdown chunking
│   ├── common.py              #   Shared utilities: config, logging, manifest
│   ├── parallel.py            #   Parallel execution helpers
│   ├── qa_pipeline.py         #   Output quality checks
│   ├── metadata.py            #   Scholarly metadata extraction
│   ├── citations.py           #   Citation graph extraction
│   ├── formula_score.py       #   Formula accuracy scoring
│   ├── ocr_quality.py         #   OCR quality evaluation
│   ├── figures.py             #   Figure reference extraction
│   ├── topics.py              #   Topic classification
│   ├── diff.py                #   Version-to-version diff reporting
│   ├── doc_type.py            #   Document type detection
│   ├── rag_export.py          #   RAG-oriented JSONL export
│   ├── multi_format.py        #   HTML / text / YAML export helpers
│   ├── ghpages.py             #   GitHub Pages site generation
│   ├── render_templates.py    #   Deterministic template rendering
│   └── plugin.py              #   Plugin system
├── configs/
│   └── pipeline.yaml          # Central configuration file
├── tests/
│   └── test_pipeline_structure.py  # 429 tests
├── data/raw/                  # Source PDF files provided by the user
├── outputs/                   # Generated outputs
│   ├── raw_md/                #   Raw Markdown
│   ├── cleaned_md/            #   Cleaned Markdown
│   └── chunks/                #   Chunked outputs
├── vscode-extension/          # VS Code extension (separate TypeScript project)
├── pyproject.toml             # Package metadata and tool configuration
├── Makefile                   # Common developer commands
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Multi-service container setup
└── requirements.txt           # Pinned runtime dependencies
```

## Troubleshooting

| Problem | Resolution |
|---------|------------|
| `ModuleNotFoundError: No module named 'scripts'` | Make sure the project was installed with `pip install -e .`. Prefer `python -m scripts.convert` over `python scripts/convert.py`. |
| `FileNotFoundError: Config file not found` | Pass a valid config path with `--config`, for example `pdf-pipeline --config configs/pipeline.yaml`. |
| Docling installation fails | Docling may require system libraries and a compiler toolchain. On Debian/Ubuntu, install `build-essential` and `poppler-utils`, or use Docker instead. |
| Memory issues on large PDFs | Verify `num_threads: 1` and `device: cpu` in `configs/pipeline.yaml`. If needed, constrain Docker resources explicitly. |
| Formulas look corrupted | `engine: dual` usually gives the best output. Compare with `--engine docling` and `--engine markitdown` when debugging. |
| Idempotency does not skip unchanged files | Check that `outputs/.manifest.json` is writable. To rebuild from scratch, run `make clean-outputs`. |

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
pyright scripts/                   # standard mode, currently 0 errors
```

### Coverage

```bash
python -m pytest tests/ --cov=scripts --cov-report=term-missing
```

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
