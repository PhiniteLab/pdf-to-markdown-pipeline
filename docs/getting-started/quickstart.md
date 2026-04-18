
# Quick Start

This page shows the shortest path from a fresh install to usable outputs.

## 1) Install CortexMark

For a lightweight first run:

```bash
pip install cortexmark
```

If you already know you need layout-aware conversion for complex academic PDFs:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

## 2) Prepare input files

The full pipeline starts from **PDF files**.

You can point CortexMark at:

- a single `.pdf`
- or a directory containing `.pdf` files

Examples:

```bash
cortexmark --input path/to/paper.pdf
cortexmark --input path/to/folder-of-pdfs
```

## 3) Run the default pipeline

```bash
cortexmark --config configs/pipeline.yaml --input data/raw
```

This runs the default stage chain:

```text
convert -> clean -> chunk -> render
```

## 4) Inspect the outputs

By default, look here:

- `outputs/raw_md/`
- `outputs/cleaned_md/`
- `outputs/chunks/`

If you enable additional stages, also inspect:

- `outputs/semantic_chunks/`
- `outputs/quality/`

## 5) Run optional analysis and validation stages

```bash
cortexmark --stages analyze validate --input data/raw
```

This produces artifacts such as:

- cross-reference reports
- algorithm extraction reports
- notation glossary reports
- formula validation reports
- scientific QA reports
- citation context reports

## 6) Use a named session (recommended for repeated work)

```bash
cortexmark --config configs/pipeline.yaml --input data/raw --session-name experiment-1
```

This isolates all data under:

```text
sessions/experiment-1/
├── data/raw/
└── outputs/
```

That same layout is used by the VS Code extension.

## Common commands

```bash
# Choose an engine
cortexmark --engine markitdown --input data/raw
cortexmark --engine docling --input data/raw
cortexmark --engine dual --input data/raw

# Run only specific stages
cortexmark --stages convert clean
cortexmark --stages analyze validate

# Force reprocessing
cortexmark --no-manifest
```

## Makefile shortcuts

```bash
make all
make analyze
make validate
make benchmark-reference
make test
make lint
```

## Module-level examples

```bash
python -m cortexmark.convert --input data/raw/paper.pdf --engine docling
python -m cortexmark.clean --input outputs/raw_md --output-dir outputs/cleaned_md
python -m cortexmark.chunk --input outputs/cleaned_md --output-dir outputs/chunks
python -m cortexmark.cross_ref --input outputs/cleaned_md
python -m cortexmark.rag_export --input outputs/chunks
```

## Next steps

- Read **[Requirements, Inputs, and Outputs](../guide/inputs-and-outputs.md)**
- Review **[Pipeline Stages](../guide/pipeline-stages.md)**
- If you prefer an editor workflow, open **[VS Code Setup](../vscode/setup.md)**
