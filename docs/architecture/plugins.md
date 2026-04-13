# Plugin System

The pipeline supports a plugin architecture that lets you add custom processing
steps without modifying core code.

## Hook Points

Plugins can attach to seven hook points in the pipeline:

| Hook | When it runs | Arguments |
|------|-------------|-----------|
| `pre_convert` | Before PDF conversion | `(input_path, config)` |
| `post_convert` | After PDF conversion | `(input_path, output_path, config)` |
| `pre_clean` | Before Markdown cleaning | `(input_path, config)` |
| `post_clean` | After Markdown cleaning | `(input_path, output_path, config)` |
| `pre_chunk` | Before chunking | `(input_path, config)` |
| `post_chunk` | After chunking | `(input_path, output_paths, config)` |
| `post_pipeline` | After all stages complete | `(config, summary)` |

## Creating a Plugin

### 1. Create a plugin directory

```bash
mkdir -p plugins
```

### 2. Write a plugin module

```python
# plugins/my_stats.py
"""Plugin that logs statistics after each stage."""

from phinitelab_pdf_pipeline.plugin import PluginBase


class StatsPlugin(PluginBase):
    name = "stats"

    def post_clean(self, input_path, output_path, config):
        text = output_path.read_text(encoding="utf-8")
        word_count = len(text.split())
        self.log.info("Cleaned %s: %d words", output_path.name, word_count)

    def post_pipeline(self, config, summary):
        self.log.info("Pipeline complete: %s", summary)
```

### 3. Register the plugin

Plugins are auto-discovered from the configured directory. Set the path in
`configs/pipeline.yaml`:

```yaml
plugins:
  directory: plugins/
```

Or pass via CLI:

```bash
python -m phinitelab_pdf_pipeline.plugin --plugin-dir plugins/ --list
```

## Plugin API

### PluginBase

All plugins must subclass `PluginBase`:

```python
class PluginBase:
    name: str              # unique plugin identifier
    log: logging.Logger    # pre-configured logger

    def pre_convert(self, input_path, config): ...
    def post_convert(self, input_path, output_path, config): ...
    def pre_clean(self, input_path, config): ...
    def post_clean(self, input_path, output_path, config): ...
    def pre_chunk(self, input_path, config): ...
    def post_chunk(self, input_path, output_paths, config): ...
    def post_pipeline(self, config, summary): ...
```

### PluginRegistry

The registry discovers and manages plugins:

```python
from phinitelab_pdf_pipeline.plugin import PluginRegistry

registry = PluginRegistry()
registry.discover("plugins/")

# Run hooks
registry.run_hook("post_clean", input_path=p, output_path=out, config=cfg)

# List registered plugins
for info in registry.list_plugins():
    print(f"{info.name}: {info.hooks}")
```

## Plugin Report

Generate a JSON report of all discovered plugins:

```bash
python -m phinitelab_pdf_pipeline.plugin --plugin-dir plugins/ --output report.json
```
