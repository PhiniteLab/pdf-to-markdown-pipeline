
# VS Code Extension — Setup and Usage

The VS Code extension gives you a session-based UI for the CortexMark pipeline.

> The extension does **not** bundle the Python backend. You must install `cortexmark` separately in a Python environment the extension can reach.

## Install the extension

### From the Visual Studio Code Marketplace

1. Open **Extensions** in VS Code
2. Search for **CortexMark Pipeline**
3. Install the published extension with ID **`PhiniteLab.cortexmark-pipeline-vscode`**

### From a VSIX file

If you prefer an offline/manual install:

1. Open the Command Palette
2. Run **Extensions: Install from VSIX...**
3. Select your `.vsix` package

## Install the Python backend

Choose one backend setup:

### Lightweight backend

```bash
pip install cortexmark
```

### Layout-aware backend

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

## Requirements

| Requirement | Why it matters | Required? |
|---|---|---|
| VS Code 1.92+ | Minimum supported editor runtime | Yes |
| Python 3.11+ | Runs the CortexMark backend | Yes |
| `cortexmark` Python package | Provides the CLI/modules the extension launches | Yes |
| `docling` extra | Needed only for `docling` / `dual` workflows | Optional |
| Poppler / Tesseract | Useful for OCR-heavy or image-heavy PDF workflows | Optional |
| A workspace folder | The extension resolves config, `.env`, and outputs relative to the workspace | Yes |

## What the extension can process

The extension is designed around **PDF-first workflows**.

You can:

- add one or more `.pdf` files to a session,
- add a folder containing PDFs,
- run the pipeline on that session,
- preview and inspect the generated Markdown and reports.

The extension also works with the backend outputs generated from those PDFs, including Markdown, chunk files, semantic chunks, and quality reports.

## Recommended workspace layout

A common workspace layout is:

```text
my-project/
├── configs/pipeline.yaml
├── data/raw/
├── outputs/
├── sessions/
└── .env
```

If you use sessions, the extension stages files under:

```text
sessions/<session-name>/data/raw/
sessions/<session-name>/outputs/
```

## First-run workflow

1. Open your project folder in VS Code
2. Install the extension
3. Make sure the backend is installed in the interpreter you want to use
4. Run **CortexMark: Environment Doctor**
5. If needed, run **CortexMark: Setup Wizard**
6. Create a new session
7. Add PDFs or add a PDF folder
8. Run **CortexMark: Run Full Pipeline**
9. Open outputs in the tree view, preview panel, or dashboard

## Settings

Path/config resolution precedence:

1. explicit VS Code setting (`cortexmark.*`)
2. process environment variables
3. workspace `.env`
4. `paths:` entries in the selected pipeline config
5. workspace-relative defaults

Python resolution precedence:

1. explicit `cortexmark.pythonPath`
2. `CORTEXMARK_PYTHON_PATH` / `CORTEXMARK_PYTHON` / `PIPELINE_PYTHON`
3. `VIRTUAL_ENV`
4. workspace `.venv` / `venv`
5. Microsoft Python extension interpreter
6. `python3` (or `python` on Windows)

| Setting | Default | Description |
|---|---|---|
| `cortexmark.pythonPath` | `python3` | Python executable override |
| `cortexmark.configPath` | `configs/pipeline.yaml` | Pipeline config path relative to the workspace |
| `cortexmark.dataRoot` | `` | Optional input root override |
| `cortexmark.outputRoot` | `` | Optional shared output root override |
| `cortexmark.sessionStorePath` | `.cortexmark/sessions.json` | Session metadata location |
| `cortexmark.defaultEngine` | `dual` | Default engine |
| `cortexmark.autoProcess` | `false` | Auto-run when new PDFs are detected |

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

## Outputs you will see in VS Code

After a run, the extension helps you browse:

- raw Markdown
- cleaned Markdown
- chunk files
- semantic chunk files
- quality reports
- dashboard metrics
- previewable Markdown outputs

## Typical daily usage

- **Run Full Pipeline** — default end-to-end processing
- **Convert Only** — PDF → Markdown only
- **Generate QA Report** — quality-focused inspection
- **Run Cross-Reference / Algorithm / Notation / Semantic Chunking** — selective analysis
- **Preview Markdown** — open a rendered preview
- **Refresh Dashboard** — reload the metrics panel

## Notes and limitations

- Keep each processing session scoped to a **single PDF folder root** when possible.
- The extension is a UI/orchestration layer; heavy lifting is still done by the Python backend.
- For the best experience, run **Environment Doctor** before your first real batch.
