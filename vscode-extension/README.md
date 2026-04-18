
# CortexMark — VS Code Extension

A VS Code extension for running the CortexMark PDF → Markdown pipeline from inside the editor.

It provides:

- session-based PDF processing,
- pipeline and analysis commands,
- Markdown preview,
- dashboard metrics,
- real-time progress and logging,
- a chat-oriented control surface.

> Important: this extension is the **UI layer only**. It does **not** bundle the Python backend. Install `cortexmark` separately.

## Install

### Install from the marketplace

1. Open VS Code
2. Open the **Extensions** view
3. Search for **CortexMark**
4. Install the published extension ID: **`PhiniteLab.cortexmark-vscode`**

### Install from VSIX

You can also install a `.vsix` package via:

```text
Ctrl/Cmd + Shift + P → Extensions: Install from VSIX...
```

## Backend requirements

The extension launches the Python backend in your workspace environment.

### Minimum backend

```bash
pip install cortexmark
```

### Recommended backend for academic PDFs

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "cortexmark[docling]"
```

### Optional system tools

- `poppler-utils` / `poppler`
- `tesseract-ocr` / `tesseract`

These are useful for OCR-heavy or image-heavy PDF workflows, but they are not required for every project.

## Requirements at a glance

| Requirement | Required? | Notes |
|---|---|---|
| VS Code 1.92+ | Yes | Minimum supported editor version |
| Python 3.11+ | Yes | Runs the backend |
| `cortexmark` package | Yes | The extension depends on the backend CLI/modules |
| `docling` extra | Optional | Needed for `docling` / `dual` workflows |
| Poppler / Tesseract | Optional | Helpful for OCR-style use cases |

## What you can process

Primary user input inside the extension:

- one or more **PDF files**
- a **folder containing PDFs**

Outputs you can inspect after processing:

- raw Markdown
- cleaned Markdown
- chunk files
- semantic chunk files
- quality reports
- previewable Markdown pages
- dashboard summaries

## First-time setup

1. Open your workspace folder in VS Code
2. Install the extension
3. Install the Python backend in the interpreter you want the extension to use
4. Run **CortexMark: Environment Doctor**
5. If needed, run **CortexMark: Setup Wizard**
6. Create a session
7. Add PDFs or add a PDF folder
8. Run **CortexMark: Run Full Pipeline**

## Daily workflow

### 1. Create or select a session

Sessions keep inputs and outputs isolated. The extension stores session metadata in:

```text
.cortexmark/sessions.json
```

Session-scoped pipeline artifacts live under:

```text
sessions/<session-name>/
├── data/raw/
└── outputs/
```

### 2. Add PDFs

Use either:

- **Add PDFs...**
- **Add PDF Folder...**

### 3. Run commands

Useful commands include:

- **Run Full Pipeline**
- **Convert Only**
- **Generate QA Report**
- **Run Cross-Reference Analysis**
- **Run Algorithm Extraction**
- **Run Notation Glossary**
- **Run Semantic Chunking**
- **Preview Markdown**
- **Refresh Dashboard**

## Settings

| Setting | Default | Description |
|---|---|---|
| `cortexmark.pythonPath` | `python3` | Python executable override |
| `cortexmark.configPath` | `configs/pipeline.yaml` | Pipeline config path |
| `cortexmark.dataRoot` | `` | Optional input root override |
| `cortexmark.outputRoot` | `` | Optional shared output root override |
| `cortexmark.sessionStorePath` | `.cortexmark/sessions.json` | Session metadata path |
| `cortexmark.defaultEngine` | `dual` | Default conversion engine |
| `cortexmark.autoProcess` | `false` | Auto-process new PDFs |

Path resolution precedence:

1. explicit VS Code setting (`cortexmark.*`)
2. process environment variables
3. workspace `.env`
4. selected pipeline config
5. workspace-relative defaults

## Commands

All commands are available from the Command Palette with the **`CortexMark:`** prefix.

Key commands:

- `Environment Doctor`
- `Setup Wizard`
- `New Session`
- `Process Active Session`
- `Run Full Pipeline`
- `Convert Only`
- `Generate QA Report`
- `Run Cross-Reference Analysis`
- `Run Algorithm Extraction`
- `Run Notation Glossary`
- `Run Semantic Chunking`
- `Preview Markdown`
- `Refresh Dashboard`

See also:

- https://github.com/PhiniteLab/pdf-to-markdown-pipeline/blob/main/docs/vscode/setup.md
- https://github.com/PhiniteLab/pdf-to-markdown-pipeline/blob/main/docs/vscode/commands.md

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

Press `F5` in VS Code to launch an Extension Development Host.
