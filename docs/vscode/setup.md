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
- Python 3.11+ with the pipeline installed (`pip install -e .` in the project root)
- `poppler-utils` and `tesseract-ocr` on the system PATH

## Settings

Open **Settings → Extensions → PhiniteLab PDF Pipeline** or edit
`settings.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `pdfPipeline.pythonPath` | `"python3"` | Python executable. Leave as `python3` for auto-detection of workspace `.venv`. |
| `pdfPipeline.configPath` | `"configs/pipeline.yaml"` | Pipeline config file path relative to workspace root. |
| `pdfPipeline.defaultEngine` | `"dual"` | Default engine: `docling`, `markitdown`, or `dual`. |
| `pdfPipeline.autoProcess` | `false` | Automatically run pipeline when new PDFs appear in `data/raw/`. |

### Example `settings.json`

```json
{
  "pdfPipeline.pythonPath": "${workspaceFolder}/.venv/bin/python",
  "pdfPipeline.configPath": "configs/pipeline.yaml",
  "pdfPipeline.defaultEngine": "dual",
  "pdfPipeline.autoProcess": false
}
```

## Sidebar Views

The extension adds a **PhiniteLab PDF Pipeline** activity bar icon with three views:

| View | Description |
|------|-------------|
| **Pipeline** | Tree view with sessions, actions, analysis modules, and outputs |
| **Dashboard** | Webview showing run statistics and output summaries |
| **Chat** | Webview chat panel for interactive Q&A about documents |
