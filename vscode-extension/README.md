# CortexMark — VS Code Extension

A VS Code extension that provides session-based batch processing for the CortexMark with a Markdown preview panel, quality dashboard, real-time progress tracking, analysis module integration, and a chat panel.

> Note: The extension UI (`.vsix`) does **not** include the Python backend. `cortexmark` must be installed separately in the user's Python environment.

## Migration Notes

This extension was renamed from **PhiniteLab PDF Pipeline** to **CortexMark**.

- Old extension ID: `phinitelab-pdf-pipeline-vscode`
- New extension ID: `cortexmark-vscode`
- Current shipped publisher in `package.json`: `PhiniteLab`

The extension display name and package ID changed, but the current shipped manifest still uses the `PhiniteLab` publisher. Existing installs may still need a **manual install/upgrade** to the `cortexmark-vscode` package. Session metadata is migrated from `.phinitelab-pdf-pipeline/sessions.json` to `.cortexmark/sessions.json` automatically when present.

## Features

- **Session management**: create, activate, and delete pipeline sessions
- **Batch PDF processing**: add individual PDFs or entire folders to a session
- **Pipeline execution**: run the full pipeline or individual stages (convert, QA, diff)
- **Analysis modules**: run Cross-Reference, Algorithm Extraction, Notation Glossary, and Semantic Chunking analyses directly from the sidebar or chat
- **Markdown preview**: side-by-side WebView panel with rendered math formulas, QA badges, and content statistics (theorem/proof/definition/algorithm/formula/figure counts)
- **Quality dashboard**: sidebar panel showing pipeline metrics — average QA score with badge breakdown, cross-reference resolution rate, algorithm counts, notation statistics
- **Progress visualization**: notification-bar progress during pipeline and analysis execution with cancellation support
- **Sidebar tree view**: sessions, files (with status icons), actions, analysis tools, and output browsing
- **Chat panel**: command-driven panel with 11 commands (English + Turkish) for pipeline control and analysis
- **Real-time logging**: output channel shows pipeline progress as it runs
- **Auto-detection**: finds workspace `.venv` for Python execution
- **File watchers**: detect new PDFs in `data/raw/` (optional auto-processing)

## Portability policy

The extension now resolves runtime paths with a portable precedence order:

1. explicit VS Code setting (`cortexmark.*`)
2. environment variables from the current VS Code process
3. workspace-root `.env`
4. `paths:` entries inside the selected pipeline config
5. workspace-relative safe defaults

For Python execution, the extension uses:

1. explicit `cortexmark.pythonPath`
2. `CORTEXMARK_PYTHON_PATH` / `CORTEXMARK_PYTHON` / `PIPELINE_PYTHON`
3. `VIRTUAL_ENV`
4. workspace `.venv` / `venv`
5. the interpreter selected by the Microsoft Python extension
6. `python3` (or `python` on Windows)

Relative values from settings, environment variables, and `.env` are resolved from the workspace root. Paths coming from `configs/pipeline.yaml` still resolve relative to the config file directory.

## Sidebar Tree Structure

```
CortexMark
├── Sessions
│   └── ★ experiment1 (active)
│       ├── ○ paper.pdf         (queued)
│       ├── ↻ textbook.pdf      (processing)
│       ├── ✓ thesis.pdf        (done)
│       └── ✗ broken.pdf        (error)
├── Actions
│   ├── ▶ Run Full Pipeline
│   ├── ▶ Convert Only
│   ├── 📊 Generate QA Report
│   ├── 🔍 Compare Two Folders
│   └── ⚙ Open Config
├── Analysis
│   ├── 🔗 Cross References
│   ├── 💻 Algorithm Extraction
│   ├── 𝑥 Notation Glossary
│   ├── ✂ Semantic Chunking
│   └── ▶▶ Run All Analyses
├── Outputs
│   ├── raw_md/
│   ├── cleaned_md/
│   ├── chunks/
│   └── quality/
├── Dashboard (webview)
│   ├── Pipeline Overview (PDF/output counts)
│   ├── Quality (badges, avg score)
│   ├── Cross References (resolution rate)
│   ├── Algorithms (count, depth)
│   └── Notation (symbols, entries)
└── Chat (webview)
    └── /status /process /qa /crossref /algorithm
        /notation /chunk /analyze /preview /help
```

## Commands

| Command | Description |
|---------|-------------|
| `Environment Doctor` | Run environment diagnostics and open the report |
| `Setup Wizard` | Guided setup for install/settings/docs actions using the extension setup guide |
| `Refresh` | Refresh sidebar tree and dashboard |
| `New Session` | Create a new processing session |
| `Delete Session` | Remove a session and its data |
| `Set as Active` | Switch the active session |
| `Process Active Session` | Run pipeline on active session |
| `Add PDFs...` | Register selected PDFs with the active session |
| `Add PDF Folder...` | Register all PDFs from a selected folder with the active session |
| `Run Full Pipeline` | Execute all stages |
| `Convert Only` | Run convert stage only |
| `Generate QA Report` | Run quality analysis |
| `Compare Two Folders` | Diff two output directories |
| `Open Config` | Open `configs/pipeline.yaml` |
| `Reveal in Explorer` | Open output folder |
| `Delete` | Delete output file or folder |
| **Run Cross-Reference Analysis** | Detect and resolve cross-references |
| **Run Algorithm Extraction** | Extract pseudocode and algorithm blocks |
| **Run Notation Glossary** | Build mathematical symbol table |
| **Run Semantic Chunking** | Theorem-aware content splitting |
| **Run All Analyses** | Execute all 4 analysis modules sequentially |
| **Preview Markdown** | Open Markdown in side preview panel |
| **Refresh Preview** | Reload the preview content |
| **Refresh Dashboard** | Reload dashboard metrics |

## Chat Commands

| Command | Turkish Alias | Description |
|---------|--------------|-------------|
| `status` | `durum` | Refresh session status |
| `process` / `run` | `çalıştır` | Run pipeline on active session |
| `qa` | `kalite` | Generate QA report |
| `crossref` | `çapraz referans` | Cross-reference analysis |
| `algorithm` / `algo` | `algoritma` | Algorithm extraction |
| `notation` / `glossary` | `notasyon` | Notation glossary |
| `chunk` / `semantic` | `bölümleme` | Semantic chunking |
| `analyze` / `all` | `analiz` | Run all analyses |
| `preview` | `önizleme` | Preview active Markdown |
| `help` | `yardım` | Show available commands |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `cortexmark.pythonPath` | `python3` | Python executable override. Leave empty or keep `python3` to allow portable discovery fallbacks. |
| `cortexmark.configPath` | `configs/pipeline.yaml` | Pipeline config file path relative to workspace root. |
| `cortexmark.dataRoot` | `` | Optional input root override. Relative values resolve from the workspace root. |
| `cortexmark.outputRoot` | `` | Optional shared output root override. When set, `raw_md`, `cleaned_md`, `chunks`, `quality`, and `semantic_chunks` live under this directory. |
| `cortexmark.sessionStorePath` | `` | Optional extension session metadata JSON override. Relative values resolve from the workspace root. Session inputs/outputs live under `sessions/<session>/...`. |
| `cortexmark.defaultEngine` | `dual` | Default conversion engine (`docling`, `markitdown`, or `dual`). |
| `cortexmark.autoProcess` | `false` | Automatically run the pipeline when new PDFs are detected. |

### Optional environment variables / `.env`

You can keep machines portable by setting overrides in the shell or in a workspace `.env` file:

```dotenv
PIPELINE_CONFIG=configs/pipeline.yaml
CORTEXMARK_PYTHON_PATH=.venv/bin/python
CORTEXMARK_DATA_ROOT=data/raw
CORTEXMARK_OUTPUT_ROOT=outputs
CORTEXMARK_SESSION_STORE_PATH=.cortexmark/sessions.json
```

Also supported for finer-grained output overrides:

- `CORTEXMARK_OUTPUT_RAW_MD`
- `CORTEXMARK_OUTPUT_CLEANED_MD`
- `CORTEXMARK_OUTPUT_CHUNKS`
- `CORTEXMARK_OUTPUT_QUALITY`
- `CORTEXMARK_OUTPUT_SEMANTIC_CHUNKS`

## Architecture

| File | Purpose |
|------|---------|
| `src/extension.ts` | Activation, command registration (includes Environment Doctor + Setup Wizard), file watchers, panel integration |
| `src/sessionManager.ts` | Session persistence (`.cortexmark/sessions.json`), event emitter |
| `src/sessionTree.ts` | Tree data provider (Sessions, Actions, Analysis, Outputs groups) |
| `src/pipelineRunner.ts` | Python subprocess spawning with progress bar, cancellation, and analysis module support |
| `src/previewPanel.ts` | Markdown preview WebView with QA badges, math rendering, and content statistics |
| `src/dashboardPanel.ts` | Quality metrics dashboard WebView with report parsing and badge visualization |
| `src/chatView.ts` | Chat panel with 11 commands (English + Turkish aliases) |
| `src/types.ts` | TypeScript interfaces (`PdfFile`, `Session`, `FileStatus`) |

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

Press `F5` in VS Code to run the extension in an Extension Development Host.

### Prerequisites

- Node.js 18+
- The Python pipeline package installed in the workspace (see main README)
- Optional engine extras: `cortexmark[docling]` for dual/docling conversion and OCR workflows
