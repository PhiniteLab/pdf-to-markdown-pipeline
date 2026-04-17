# VS Code Extension — Setup

## Installation

### From VSIX (recommended)

1. Build the extension:

    ```bash
    cd vscode-extension
    npm install && npm run compile
    npx @vscode/vsce package
    ```

2. Install the `.vsix` file in VS Code:

    ```
    Ctrl+Shift+P → Extensions: Install from VSIX…
    ```

### From source (development)

```bash
cd vscode-extension
npm install
npm run compile
```

Press **F5** in VS Code to launch an Extension Development Host.

## Requirements

- VS Code **1.92** or later
- Python 3.11+ with the pipeline installed (`pip install cortexmark` in the target interpreter)
- `poppler-utils` and `tesseract-ocr` on the system PATH

> Important: The `.vsix` package only contains the VS Code extension (UI). It does **not** bundle the Python backend package (`cortexmark`). Backend setup must be completed on the target machine.

## Recommended setup workflow

1. Open workspace
2. Run **CortexMark: Environment Doctor** (`cortexmark.checkEnvironment`)
   to get a diagnostics report in the `CortexMark Environment` output channel.
3. If checks fail, run **CortexMark: Setup Wizard** (`cortexmark.setupWizard`) for quick remediation actions.
   The wizard links back to this extension-specific setup guide and only offers one-click backend install when the resolved interpreter is actually runnable.
4. Keep each processing session scoped to a **single PDF folder root**. The current extension patch blocks mixing PDFs from different directories in one session to avoid ambiguous backend input paths.

## Settings

Open **Settings → Extensions → CortexMark** or edit
`settings.json`:

Path/config resolution follows this precedence:

1. explicit VS Code setting (`cortexmark.*`)
2. process environment variables
3. workspace `.env`
4. `paths:` entries in the selected pipeline config
5. workspace-relative defaults

Python resolution follows:

1. explicit `cortexmark.pythonPath`
2. `CORTEXMARK_PYTHON_PATH` / `CORTEXMARK_PYTHON` / `PIPELINE_PYTHON`
3. `VIRTUAL_ENV`
4. workspace `.venv` / `venv`
5. Microsoft Python extension interpreter
6. `python3` (or `python` on Windows)

| Setting | Default | Description |
|---------|---------|-------------|
| `cortexmark.pythonPath` | `"python3"` | Python executable override. Leave empty or as `python3` to keep portable discovery fallbacks enabled. |
| `cortexmark.configPath` | `"configs/pipeline.yaml"` | Pipeline config file path relative to workspace root. |
| `cortexmark.dataRoot` | `""` | Optional input root override. Relative values resolve from the workspace root. |
| `cortexmark.outputRoot` | `""` | Optional shared output root override. When set, extension outputs are derived under this directory. |
| `cortexmark.sessionStorePath` | `".cortexmark/sessions.json"` | Optional absolute/relative path to extension session metadata JSON. Relative values are resolved with workspace root. |
| `cortexmark.defaultEngine` | `"dual"` | Default engine: `docling`, `markitdown`, or `dual`. |
| `cortexmark.autoProcess` | `false` | Automatically run pipeline when new PDFs appear in `data/raw/`. |

### Example `settings.json`

```json
{
  "cortexmark.pythonPath": "${workspaceFolder}/.venv/bin/python",
  "cortexmark.configPath": "configs/pipeline.yaml",
  "cortexmark.dataRoot": "data/raw",
  "cortexmark.outputRoot": "outputs",
  "cortexmark.sessionStorePath": ".cortexmark/sessions.json",
  "cortexmark.defaultEngine": "dual",
  "cortexmark.autoProcess": false
}
```

> On Windows, set `cortexmark.pythonPath` explicitly (for example:
> `${workspaceFolder}\\.venv\\Scripts\\python.exe`).

### Optional `.env` / environment overrides

Instead of committing machine-specific absolute paths into VS Code settings, you can place overrides in the workspace `.env`:

```dotenv
PIPELINE_CONFIG=configs/pipeline.yaml
CORTEXMARK_PYTHON_PATH=.venv/bin/python
CORTEXMARK_DATA_ROOT=data/raw
CORTEXMARK_OUTPUT_ROOT=outputs
CORTEXMARK_SESSION_STORE_PATH=.cortexmark/sessions.json
```

Supported output-specific overrides:

- `CORTEXMARK_OUTPUT_RAW_MD`
- `CORTEXMARK_OUTPUT_CLEANED_MD`
- `CORTEXMARK_OUTPUT_CHUNKS`
- `CORTEXMARK_OUTPUT_QUALITY`
- `CORTEXMARK_OUTPUT_SEMANTIC_CHUNKS`

Relative values from settings, environment variables, and `.env` resolve from the workspace root. `paths:` values inside `pipeline.yaml` continue to resolve relative to the config file directory.

### Engine-specific install notes

- `markitdown`: `pip install cortexmark`
- `docling`: `pip install "cortexmark[docling]"`
- `dual`: use `cortexmark[docling]` if you want docling-assisted conversion available.

## Sidebar Views

The extension adds a **CortexMark** activity bar icon with three views:

| View | Description |
|------|-------------|
| **Pipeline** | Tree view with sessions, actions, analysis modules, and outputs |
| **Dashboard** | Webview showing run statistics and output summaries |
| **Chat** | Webview chat panel for interactive Q&A about documents |

When a pipeline run uses a session name, quality artifacts are expected under
`outputs/quality/<session-name>/`.
