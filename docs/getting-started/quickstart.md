# Quick Start

This page shows the shortest **actually runnable** path from a fresh install to usable outputs.

## Option A — Fresh workspace + pip install

If you installed CortexMark from PyPI, start by creating a small working directory with your own config file.

### 1) Install CortexMark

For a lightweight first run:

```bash
pip install cortexmark
```

If you already know you need layout-aware conversion for complex academic PDFs:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

### 2) Create a working directory

```bash
mkdir -p my-cortexmark-project/configs
mkdir -p my-cortexmark-project/data/raw
cd my-cortexmark-project
```

### 3) Create `configs/pipeline.yaml`

Save this minimal config as `configs/pipeline.yaml`:

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
  engine: dual

idempotency:
  enabled: true
  manifest_file: outputs/.manifest.json
```

### 4) Add input PDFs

Put one or more PDFs under `data/raw/`, for example:

```text
my-cortexmark-project/
├── configs/pipeline.yaml
└── data/raw/
    └── paper.pdf
```

### 5) Run the default pipeline

```bash
cortexmark --config configs/pipeline.yaml --input data/raw
```

This runs the default stage chain:

```text
convert -> clean -> chunk -> render
```

### 6) Inspect the outputs

Look here:

- `outputs/raw_md/`
- `outputs/cleaned_md/`
- `outputs/chunks/`

If you enable additional stages, also inspect:

- `outputs/semantic_chunks/`
- `outputs/quality/`

### 7) Run optional analysis and validation

```bash
cortexmark --config configs/pipeline.yaml --stages analyze validate --input data/raw
```

This produces artifacts such as:

- cross-reference reports
- algorithm extraction reports
- notation glossary reports
- formula validation reports
- scientific QA reports
- citation context reports

### 8) Use a named session (recommended for repeated work)

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

## Option B — Cloned repository workflow

If you cloned the repository, you can use the checked-in config and Makefile helpers directly:

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then use:

```bash
make all
make analyze
make validate
make benchmark-reference
make test
make lint
```

## Common commands

```bash
# Choose an engine
cortexmark --config configs/pipeline.yaml --engine markitdown --input data/raw
cortexmark --config configs/pipeline.yaml --engine docling --input data/raw
cortexmark --config configs/pipeline.yaml --engine dual --input data/raw

# Run only specific stages
cortexmark --config configs/pipeline.yaml --stages convert clean --input data/raw
cortexmark --config configs/pipeline.yaml --stages analyze validate --input data/raw

# Force reprocessing
cortexmark --config configs/pipeline.yaml --no-manifest --input data/raw
```

## Module-level examples

```bash
python -m cortexmark.convert --config configs/pipeline.yaml --input data/raw/paper.pdf --engine docling
python -m cortexmark.clean --config configs/pipeline.yaml --input outputs/raw_md --output-dir outputs/cleaned_md
python -m cortexmark.chunk --config configs/pipeline.yaml --input outputs/cleaned_md --output-dir outputs/chunks
python -m cortexmark.cross_ref --config configs/pipeline.yaml --input outputs/cleaned_md
python -m cortexmark.rag_export --config configs/pipeline.yaml --input outputs/chunks
```

## Next steps

- Read **[Requirements, Inputs, and Outputs](../guide/inputs-and-outputs.md)**
- Review **[Pipeline Stages](../guide/pipeline-stages.md)**
- If you prefer an editor workflow, open **[VS Code Setup](../vscode/setup.md)**
