# Configuration

The pipeline is configured via `configs/pipeline.yaml`. Every CLI flag can also
be set in this file.

## Full Configuration Reference

```yaml
# Course / project identifier (used for output sub-directories)
course_id: mkt4822-RL

# Directory paths
paths:
  data_raw: data/raw
  output_raw_md: outputs/raw_md
  output_cleaned_md: outputs/cleaned_md
  output_chunks: outputs/chunks

# Conversion settings
convert:
  engine: dual          # docling | markitdown | dual
  docling:
    device: auto        # auto | cpu | cuda
    do_ocr: true
    ocr_lang: eng

# Cleaning rules
clean:
  header_pattern: "^Page \\d+"
  footer_pattern: "^\\d+$"
  max_blank_lines: 2

# Chunking settings
chunk:
  split_levels: [1, 2]  # heading levels to split on

# Template rendering
render_templates:
  syllabus_file: "00_meta/MKT4822_syllabus.md"

# Logging
logging:
  level: INFO             # DEBUG | INFO | WARNING | ERROR
  format: "%(levelname)s %(name)s: %(message)s"

# Idempotency (skip already processed files)
idempotency:
  enabled: true
  manifest_file: outputs/.manifest.json
```

## Environment Variable Overrides

| Variable | Overrides | Example |
|----------|-----------|---------|
| `PIPELINE_CONFIG` | `--config` path | `export PIPELINE_CONFIG=configs/prod.yaml` |
| `PIPELINE_ENGINE` | `convert.engine` | `export PIPELINE_ENGINE=docling` |

## Per-Module Configuration

Each module reads its section from the config:

```python
cfg = load_config(args.config)
chunk_cfg = cfg.get("chunk", {})
split_levels = chunk_cfg.get("split_levels", [1, 2])
```

## Idempotency

When `idempotency.enabled` is `true`, the pipeline tracks processed files in a
JSON manifest and skips them on re-run. Use `--no-manifest` to force
reprocessing:

```bash
phinitelab-pdf-pipeline --config configs/pipeline.yaml --no-manifest
```
