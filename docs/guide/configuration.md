# Configuration

The pipeline is configured via `configs/pipeline.yaml`.

## Full Configuration Reference

```yaml
# Generic source identifier used for default input/output scoping
source_id: default


paths:
  data_raw: data/raw
  output_raw_md: outputs/raw_md
  output_cleaned_md: outputs/cleaned_md
  output_chunks: outputs/chunks
  output_quality: outputs/quality
  output_semantic_chunks: outputs/semantic_chunks

convert:
  engine: dual          # docling | markitdown | dual
  docling:
    device: auto        # auto | cpu | cuda
    do_ocr: true
    ocr_lang: eng

clean:
  header_pattern: "^Page \\d+"
  footer_pattern: "^\\d+$"
  max_blank_lines: 2

chunk:
  split_levels: [1, 2]

render_templates:
  outline_file: "00_meta/outline.md"
  max_summary_chars: 240
  max_scope_items: 6
  max_tasks: 5

logging:
  level: INFO
  format: "%(levelname)s %(name)s: %(message)s"

idempotency:
  enabled: true
  manifest_file: outputs/.manifest.json
```

## Environment Variable Overrides

| Variable | Overrides | Example |
|----------|-----------|---------|
| `PIPELINE_CONFIG` | default config path (`--config` still wins) | `export PIPELINE_CONFIG=configs/prod.yaml` |
| `PIPELINE_ENGINE` | convert engine (`--engine` still wins) | `export PIPELINE_ENGINE=docling` |

## Per-Module Configuration

Each module reads only its own section:

```python
cfg = load_config(args.config)
chunk_cfg = cfg.get("chunk", {})
split_levels = chunk_cfg.get("split_levels", [1, 2])
```

## Session-Aware Outputs

When you run the orchestrator with `--session-name`, stage outputs are scoped by session:

- `outputs/raw_md/<session>/<source_id>/...`
- `outputs/cleaned_md/<session>/<source_id>/...`
- `outputs/chunks/<session>/<source_id>/...`
- `outputs/quality/<session>/*.json`

Without `--session-name`, outputs remain under the non-session base directories.

## Idempotency

When `idempotency.enabled` is `true`, the pipeline tracks processed files in a
JSON manifest and skips unchanged inputs. Use `--no-manifest` to force
reprocessing:

```bash
cortexmark --config configs/pipeline.yaml --no-manifest
```
