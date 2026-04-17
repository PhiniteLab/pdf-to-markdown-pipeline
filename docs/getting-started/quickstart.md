# Quick Start

## Basic Usage

Place your PDF files under `data/raw/` and run the pipeline:

```bash
cortexmark --config configs/pipeline.yaml
```

Or use Makefile shortcuts:

```bash
make all          # convert → clean → chunk → render
make convert      # PDF → raw Markdown
make clean        # normalize raw Markdown
make chunk        # split into logical sections
make render       # populate templates
make analyze      # semantic chunk + cross-ref + algorithm + notation
make validate     # formula validation + scientific QA + citation context
```

## Run Individual Modules

```bash
# Convert a single PDF
python -m cortexmark.convert --input data/raw/paper.pdf --engine docling

# Clean a directory
python -m cortexmark.clean --input outputs/raw_md/ --output-dir outputs/cleaned_md/

# Chunk cleaned Markdown
python -m cortexmark.chunk --input outputs/cleaned_md/ --output-dir outputs/chunks/

# Analyze for cross-references
python -m cortexmark.cross_ref --input outputs/cleaned_md/
```

## Custom Input Path

Process a specific file or directory outside the default data path:

```bash
cortexmark --config configs/pipeline.yaml --input /path/to/my/docs/
```

## Session Support

Name sessions to create an isolated session workspace under `sessions/<session>/...`:

```bash
cortexmark --config configs/pipeline.yaml --session-name experiment-1
```

## Stage Selection

Run only specific stages:

```bash
cortexmark --stages convert clean
cortexmark --stages analyze validate
```

Available stages: `convert`, `clean`, `chunk`, `render`, `analyze`, `validate`.
