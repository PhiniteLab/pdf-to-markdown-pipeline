# PhiniteLab PDF Pipeline

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
- **Template rendering**: deterministic syllabus and week template population
- **Docker support**: containerized execution with minimal setup
- **VS Code extension**: session management, Markdown preview panel, quality dashboard, analysis module integration, progress visualization, and chat panel with 22 commands
- **Validated by 755 tests** with a minimum coverage threshold of 70%

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

### Install with pip (lightweight, CPU-only)

The default installation is lightweight and does **not** include Docling, PyTorch,
or any GPU/CUDA packages. It provides the `markitdown` conversion engine:

```bash
pip install git+https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
```

This is sufficient for running the pipeline with `--engine markitdown`.

### Install with Docling engine (CPU)

To use the `docling` or `dual` conversion engine on **CPU**, first install
CPU-only PyTorch, then install the package with the `[docling]` extra:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "phinitelab-pdf-pipeline[docling] @ git+https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git"
```

> **Note:** Pre-installing CPU-only PyTorch prevents pip from downloading the
> much larger GPU-enabled build (~2 GB+) from PyPI.

### Install with GPU support

If you have an NVIDIA GPU with CUDA, you can install with GPU support directly:

```bash
pip install "phinitelab-pdf-pipeline[gpu] @ git+https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git"
```

This pulls the default PyTorch from PyPI, which includes CUDA support on Linux.
To target a specific CUDA version (e.g. CUDA 12.8):

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install "phinitelab-pdf-pipeline[gpu] @ git+https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git"
```

### Which installation should I choose?

| Scenario | Command |
|----------|---------|
| Lightweight / markitdown only | `pip install phinitelab-pdf-pipeline` |
| Docling engine on CPU | Pre-install CPU torch, then `pip install "phinitelab-pdf-pipeline[docling]"` |
| Docling engine with NVIDIA GPU | `pip install "phinitelab-pdf-pipeline[gpu]"` |

### WSL / Linux notes

- On WSL2 with GPU passthrough, the `[gpu]` extra works if NVIDIA drivers are
  properly configured on the Windows host.
- On headless Linux servers without a GPU, always use the CPU installation path
  to avoid pulling unnecessary CUDA libraries.

### Developer installation

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
```

This installs the runtime dependencies together with Docling and the development toolchain, including pytest, pytest-cov, Ruff, Pyright, and pre-commit.

### Install with Docker

```bash
docker compose up pipeline        # Run the pipeline
docker compose --profile test up  # Run the test profile
```

## Usage

### CLI command

After installation, you can use the `phinitelab-pdf-pipeline` command:

```bash
# Run all stages in order
phinitelab-pdf-pipeline

# Run only selected stages
phinitelab-pdf-pipeline --stages convert clean

# Use a different config file
phinitelab-pdf-pipeline --config configs/pipeline.yaml

# Select a conversion engine
phinitelab-pdf-pipeline --engine docling      # Docling only
phinitelab-pdf-pipeline --engine markitdown   # markitdown only
phinitelab-pdf-pipeline --engine dual         # combined mode (default)

# Custom input directory or single file
phinitelab-pdf-pipeline --input path/to/my.pdf

# Session-scoped output directories
phinitelab-pdf-pipeline --session-name experiment1

# Disable idempotency (force reprocess)
phinitelab-pdf-pipeline --no-manifest
```

Run `phinitelab-pdf-pipeline --help` to view all available arguments.

### Makefile shortcuts

```bash
make help           # List available commands
make all            # Run the full pipeline
make convert        # Run only PDF → Markdown conversion
make clean          # Run only the cleaning stage
make chunk          # Run only chunk generation
make render         # Run only template rendering
make test           # Run the test suite
make lint           # Run Ruff lint and formatting checks
make format         # Apply automatic formatting fixes
make clean-outputs  # Remove all generated outputs
```

### Run modules directly

Each module can also be executed independently:

```bash
# Core stages
python -m phinitelab_pdf_pipeline.convert --config configs/pipeline.yaml
python -m phinitelab_pdf_pipeline.clean --config configs/pipeline.yaml
python -m phinitelab_pdf_pipeline.chunk --config configs/pipeline.yaml
python -m phinitelab_pdf_pipeline.render_templates --config configs/pipeline.yaml

# Quality & analysis
python -m phinitelab_pdf_pipeline.qa_pipeline --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.ocr_quality --input outputs/raw_md
python -m phinitelab_pdf_pipeline.formula_score --input outputs/raw_md

# Metadata & classification
python -m phinitelab_pdf_pipeline.metadata --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.citations --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.doc_type --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.topics --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.figures --input outputs/cleaned_md

# Export & output
python -m phinitelab_pdf_pipeline.rag_export --input outputs/chunks
python -m phinitelab_pdf_pipeline.multi_format --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.ghpages --input outputs/cleaned_md
python -m phinitelab_pdf_pipeline.diff --old outputs/v1 --new outputs/v2

# Utilities
python -m phinitelab_pdf_pipeline.parallel --help
python -m phinitelab_pdf_pipeline.plugin --help
```

## Pipeline Stages

```text
PDF files
   │
   ▼
┌──────────┐   raw_md/    ┌───────┐  cleaned_md/  ┌───────┐  chunks/
│ convert  │ ───────────►  │ clean │ ────────────►  │ chunk │ ──────────► output
│ (dual)   │               │       │                │       │
└──────────┘               └───────┘                └───────┘
                                                        │
                                                        ▼
                                                ┌───────────────┐
                                                │    render      │
                                                │  (templates)   │
                                                └───────────────┘
```

1. **convert**: PDF → raw Markdown. Docling handles structure (headings, formulas, algorithms), while markitdown fills text gaps via fingerprint-based deduplication.
2. **clean**: removes page numbers, repeated headers/footers, and broken line wraps. Normalizes heading hierarchy and table blocks.
3. **chunk**: splits cleaned Markdown into logical sections based on heading levels (default: H1 and H2). Files are numbered (e.g., `chunk_001_Introduction.md`).
4. **render** *(optional)*: fills course and week template files deterministically from syllabus content.
5. **analyze** *(optional)*: runs semantic chunking, cross-reference analysis, algorithm extraction, and notation glossary on cleaned Markdown.
6. **validate** *(optional)*: runs formula validation, scientific QA checks, and citation context analysis. Produces quality reports under `outputs/quality/`.

### Optional Analysis Modules

| Module | Purpose | Output |
|--------|---------|--------|
| `qa_pipeline` | Encoding errors, missing text, broken links, orphan headings, table integrity | Markdown/JSON report with GOLD/SILVER/BRONZE/FAIL badges |
| `ocr_quality` | Garble count, symbol-soup, repeat artifacts, common-word ratio | A–F confidence grade (0–1 score) |
| `formula_score` | Recovered equations, incomplete markers, balanced parentheses | Per-file fidelity percentage |
| `metadata` | Title, authors, abstract, keywords, DOI, journal, year, emails, funding | YAML front-matter, BibTeX, APA7 |
| `citations` | Author-year and numeric `[1,2,3]` citation patterns | JSON graph, Graphviz DOT |
| `doc_type` | Document type (paper, textbook, syllabus, slides, report, generic) | Type, confidence (0–1), detection signals |
| `topics` | Topic distribution (RL, ML, NLP, CV, optimization, etc.) | Per-file and aggregated distribution |
| `figures` | Markdown `![alt](src)` and HTML `<img>` image references | JSON manifest, Markdown gallery |
| `diff` | File tree comparison with unified diff | JSON change statistics |
| `rag_export` | RAG-ready chunks with SHA-256 IDs, token estimates, entity types, formulas, cross-refs | JSONL or JSON array |
| `semantic_chunk` | Scientific-aware chunking: theorems, proofs, definitions, algorithms, examples | Numbered chunk files with entity metadata |
| `cross_ref` | Cross-reference resolution: definition sites, mention detection, kind normalization | JSON report with resolution rate, unresolved refs |
| `algorithm_extract` | Algorithm/pseudocode extraction: fenced blocks, header lines, input/output/step parsing | JSON report with algorithm structures |
| `notation_glossary` | Mathematical notation glossary: explicit definitions, list/table notations, common LaTeX symbols | JSON report, Markdown glossary table |
| `formula_validate` | Enhanced LaTeX formula validation: balanced delimiters, environment matching, command validation, complexity scoring | JSON report with per-formula issues |
| `citation_context` | Citation context extraction: purpose classification (7 categories), co-citation analysis, self-citation detection | JSON report with sentence-level context |
| `scientific_qa` | Scientific document QA: theorem-proof pairing, definition-before-use, notation consistency, algorithm validity, formula quality gate | JSON report with GOLD/SILVER/BRONZE/FAIL badges |
| `multi_format` | HTML, plain text, YAML with front-matter | Standalone pages per document |
| `ghpages` | GitHub Pages-compatible static site | HTML index with document cards |
| `parallel` | Thread/process pool abstraction with timing | `TaskResult` and `ParallelReport` |
| `plugin` | Custom hooks via file-based discovery in `plugins/` | Hook-based extensibility |

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
├── phinitelab_pdf_pipeline/           # Python package
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
│   └── test_pipeline_structure.py     # 755 tests (70% minimum coverage)
├── data/raw/                          # Source PDF files (user-provided)
│   ├── books/
│   ├── lecture_notes/
│   ├── manuscripts/
│   ├── reports/
│   ├── textbooks/chapters/
│   └── theses/
├── outputs/                           # Generated outputs
│   ├── raw_md/                        #   Raw Markdown from conversion
│   ├── cleaned_md/                    #   Cleaned and normalized Markdown
│   └── chunks/                        #   Chunked output sections
├── vscode-extension/                  # VS Code extension v0.3.0 (TypeScript)
│   ├── src/extension.ts               #   Activation, 22 commands, file watchers
│   ├── src/sessionManager.ts          #   Session persistence and events
│   ├── src/sessionTree.ts             #   Tree data provider (Sessions, Actions, Analysis, Outputs)
│   ├── src/pipelineRunner.ts          #   Subprocess spawning with progress bar & cancellation
│   ├── src/previewPanel.ts            #   Markdown preview WebView with QA badges & math
│   ├── src/dashboardPanel.ts          #   Quality metrics dashboard WebView
│   ├── src/chatView.ts                #   Chat panel (11 commands, EN + TR)
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
| `ImportError: The 'docling' package is required` | Docling is not included in the default installation. Install it with `pip install "phinitelab-pdf-pipeline[docling]"` or `pip install "phinitelab-pdf-pipeline[gpu]"`. |
| `ModuleNotFoundError: No module named 'phinitelab_pdf_pipeline'` | Make sure the project was installed with `pip install -e .`. Prefer `python -m phinitelab_pdf_pipeline.convert` over `python phinitelab_pdf_pipeline/convert.py`. |
| `FileNotFoundError: Config file not found` | Pass a valid config path with `--config`, for example `phinitelab-pdf-pipeline --config configs/pipeline.yaml`. |
| Docling installation fails | Docling may require system libraries and a compiler toolchain. On Debian/Ubuntu, install `build-essential` and `poppler-utils`, or use Docker instead. |
| Memory issues on large PDFs | Verify `num_threads: 1` and `device: cpu` in `configs/pipeline.yaml`. If needed, constrain Docker resources explicitly. |
| Formulas look corrupted | `engine: dual` usually gives the best output. Compare with `--engine docling` and `--engine markitdown` when debugging. |
| Idempotency does not skip unchanged files | Check that `outputs/.manifest.json` is writable. To rebuild from scratch, run `make clean-outputs`. |
| Tests fail after code changes | Run `make lint && make test && pyright phinitelab_pdf_pipeline/` to check all quality gates. |

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
pyright phinitelab_pdf_pipeline/   # standard mode, currently 0 errors, 0 warnings
```

### Coverage

```bash
python -m pytest tests/ --cov=phinitelab_pdf_pipeline --cov-report=term-missing
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
