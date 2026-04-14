# Plugin System

The pipeline supports file-based plugins without changing core modules.

## Hook Points

Plugins can override these hooks:

- `pre_convert`
- `post_convert`
- `pre_clean`
- `post_clean`
- `pre_chunk`
- `post_chunk`
- `post_pipeline`

Each hook receives and returns a single mutable context object:

```python
dict[str, Any]
```

## Creating a Plugin

```python
from cortexmark.plugin import PluginBase


class StatsPlugin(PluginBase):
    name = "stats"
    description = "Collects simple stage metrics"

    def post_clean(self, context: dict[str, object]) -> dict[str, object]:
        output_path = context.get("output_path")
        context["stats_enabled"] = True
        context["cleaned_output"] = str(output_path) if output_path else ""
        return context
```

## Discovery and Reporting

Plugins are discovered from `plugins/*.py` (excluding files that start with `_`):

```bash
python -m cortexmark.plugin --plugin-dir plugins/ --list
python -m cortexmark.plugin --plugin-dir plugins/ --output plugins.json
```

The JSON report contains plugin metadata and overridden hook names.
