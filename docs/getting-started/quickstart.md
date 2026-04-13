# Quick Start

## Basic Usage

Place your PDF files under `data/raw/` and run the pipeline:

```bash
phinitelab-pdf-pipeline --config configs/pipeline.yaml
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
python -m phinitelab_pdf_pipeline.convert --input data/raw/paper.pdf --engine docling

# Clean a directory
python -m phinitelab_pdf_pipeline.clean --input outputs/raw_md/ --output-dir outputs/cleaned_md/

# Chunk cleaned Markdown
python -m phinitelab_pdf_pipeline.chunk --input outputs/cleaned_md/ --output-dir outputs/chunks/

# Analyze for cross-references
python -m phinitelab_pdf_pipeline.cross_ref --input outputs/cleaned_md/
```

## Custom Input Path

Process a specific file or directory outside the default data path:

```bash
phinitelab-pdf-pipeline --config configs/pipeline.yaml --input /path/to/my/docs/
```

## Session Support

Name sessions to scope output directories:

```bash
phinitelab-pdf-pipeline --config configs/pipeline.yaml --session-name experiment-1
```

## Stage Selection

Run only specific stages:

```bash
phinitelab-pdf-pipeline --stages convert clean
phinitelab-pdf-pipeline --stages analyze validate
```

Available stages: `convert`, `clean`, `chunk`, `render`, `analyze`, `validate`.
