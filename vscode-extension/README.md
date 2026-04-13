# PhiniteLab PDF Pipeline — VS Code Extension

A VS Code extension that provides session-based batch processing for the PhiniteLab PDF Pipeline with a Markdown preview panel, quality dashboard, real-time progress tracking, analysis module integration, and a chat panel.

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

## Sidebar Tree Structure

```
PhiniteLab PDF Pipeline
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
| `Refresh` | Refresh sidebar tree and dashboard |
| `New Session` | Create a new processing session |
| `Delete Session` | Remove a session and its data |
| `Set as Active` | Switch the active session |
| `Process Active Session` | Run pipeline on active session |
| `Add PDFs...` | Add PDF files to active session |
| `Add PDF Folder...` | Add a folder of PDFs |
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
| `pdfPipeline.pythonPath` | `python3` | Python executable. Leave empty for workspace `.venv` auto-detection. |
| `pdfPipeline.configPath` | `configs/pipeline.yaml` | Pipeline config file path relative to workspace root. |
| `pdfPipeline.defaultEngine` | `dual` | Default conversion engine (`docling`, `markitdown`, or `dual`). |
| `pdfPipeline.autoProcess` | `false` | Automatically run the pipeline when new PDFs are detected. |

## Architecture

| File | Purpose |
|------|---------|
| `src/extension.ts` | Activation, command registration (22 commands), file watchers, panel integration |
| `src/sessionManager.ts` | Session persistence (`.phinitelab-pdf-pipeline/sessions.json`), event emitter |
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
