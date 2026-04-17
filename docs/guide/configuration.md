# Configuration

The pipeline is configured via `configs/pipeline.yaml`, but runtime path resolution now follows a portable precedence order:

1. CLI arguments
2. Environment variables
3. `.env` in the project root
4. `configs/pipeline.yaml`
5. Repo-relative defaults

## VS Code extension path resolution (first patch)

For the VS Code extension, effective paths are resolved with a small policy layer:

- explicit `cortexmark.*` settings are highest priority
- environment variables are checked next
- workspace `.env` is checked after environment variables
- `data_raw` / `output_*` entries inside the selected config provide config-level defaults
- `cortexmark.sessionStorePath` (or env equivalent) can move the session metadata file

Resolution rules:

1. Precedence is: explicit setting → env vars → workspace `.env` → config file → safe default.
2. Absolute paths are used as-is.
3. Relative settings and env values support `${workspaceFolder}` / `${workspaceFolderBasename}` tokens.
4. Relative settings and env values resolve from the workspace root.
5. Relative `paths:` values inside `pipeline.yaml` resolve from the config file directory.
6. Safe fallbacks are always applied:
   - `configs/pipeline.yaml`
   - `data/raw`
   - `outputs/raw_md`
   - `outputs/cleaned_md`
   - `outputs/chunks`
   - `outputs/quality`
   - `outputs/semantic_chunks`

Python interpreter resolution in the VS Code extension follows:

1. explicit `cortexmark.pythonPath`
2. `CORTEXMARK_PYTHON_PATH` / `CORTEXMARK_PYTHON` / `PIPELINE_PYTHON`
3. `VIRTUAL_ENV`
4. workspace `.venv` / `venv`
5. Microsoft Python extension interpreter
6. `python3` (or `python` on Windows)

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
| `CORTEXMARK_CONFIG` / `PIPELINE_CONFIG` | default config path (`--config` still wins) | `export CORTEXMARK_CONFIG=configs/prod.yaml` |
| `PIPELINE_ENGINE` | convert engine (`--engine` still wins) | `export PIPELINE_ENGINE=docling` |
| `PROJECT_ROOT` | project root discovery | `export PROJECT_ROOT=/srv/cortexmark` |
| `DATA_DIR` | shared data root | `export DATA_DIR=/mnt/pdfs` |
| `OUTPUT_DIR` | shared output root (`raw_md`, `cleaned_md`, `chunks`, `quality`, `semantic_chunks`) | `export OUTPUT_DIR=/tmp/cortexmark-output` |
| `REPORT_DIR` | quality/report directory | `export REPORT_DIR=/tmp/cortexmark-output/quality` |
| `LOG_DIR` | log directory | `export LOG_DIR=/var/log/cortexmark` |
| `CHECKPOINT_DIR` | checkpoints/artifacts | `export CHECKPOINT_DIR=/mnt/checkpoints` |
| `CACHE_DIR` | cache directory | `export CACHE_DIR=/tmp/cortexmark-cache` |
| `MODEL_DIR` | model/artifact directory | `export MODEL_DIR=/opt/models` |
| `EXTERNAL_BIN_DIR` | directory searched before `PATH` for external tools | `export EXTERNAL_BIN_DIR=/opt/cortexmark/bin` |
| `RAW_DATA_DIR`, `OUTPUT_RAW_MD`, `OUTPUT_CLEANED_MD`, `OUTPUT_CHUNKS`, `OUTPUT_SEMANTIC_CHUNKS`, `MANIFEST_FILE` | direct path overrides for specific pipeline locations | `export OUTPUT_CLEANED_MD=/mnt/run-42/cleaned` |

### VS Code extension environment overrides

These can be exported in the shell or placed in the workspace `.env`:

| Variable | Purpose |
|----------|---------|
| `CORTEXMARK_CONFIG_PATH` / `PIPELINE_CONFIG` | extension config path override |
| `CORTEXMARK_PYTHON_PATH` / `CORTEXMARK_PYTHON` / `PIPELINE_PYTHON` | extension Python executable override |
| `VIRTUAL_ENV` | virtualenv root used to derive the interpreter |
| `CORTEXMARK_DATA_ROOT` | extension input root override |
| `CORTEXMARK_OUTPUT_ROOT` | shared extension output root override |
| `CORTEXMARK_OUTPUT_RAW_MD` | raw Markdown output override |
| `CORTEXMARK_OUTPUT_CLEANED_MD` | cleaned Markdown output override |
| `CORTEXMARK_OUTPUT_CHUNKS` | chunk output override |
| `CORTEXMARK_OUTPUT_QUALITY` | quality-report output override |
| `CORTEXMARK_OUTPUT_SEMANTIC_CHUNKS` | semantic chunk output override |
| `CORTEXMARK_SESSION_STORE_PATH` / `CORTEXMARK_SESSION_STORE` | extension session metadata path override |

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

The session manifest and extension session store can be overridden with extension
settings in VS Code:

- `cortexmark.sessionStorePath` → session metadata JSON path (`.cortexmark/sessions.json` by default).
