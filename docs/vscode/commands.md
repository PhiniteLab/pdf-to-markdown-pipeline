# VS Code Extension — Commands

All commands are accessible via the **Command Palette** (`Ctrl+Shift+P`) with the
`PDF Pipeline:` prefix, or through the sidebar tree view icons.

## Session Management

| Command | Title | Description |
|---------|-------|-------------|
| `pdfPipeline.newSession` | New Session | Create a named session to scope inputs and outputs |
| `pdfPipeline.setActiveSession` | Set as Active | Mark a session as the active session |
| `pdfPipeline.deleteSession` | Delete Session | Remove a session and its data |
| `pdfPipeline.processSession` | Process Active Session | Run the full pipeline on the active session |

## File Management

| Command | Title | Description |
|---------|-------|-------------|
| `pdfPipeline.addPdf` | Add PDFs… | Open file picker to add PDF files to `data/raw/` |
| `pdfPipeline.addFolder` | Add PDF Folder… | Open folder picker to add all PDFs from a directory |
| `pdfPipeline.openOutput` | Reveal in Explorer | Open an output folder in the VS Code file explorer |
| `pdfPipeline.deleteOutput` | Delete | Remove output files or directories |
| `pdfPipeline.openConfig` | Open Config | Open `configs/pipeline.yaml` in the editor |

## Pipeline Execution

| Command | Title | Description |
|---------|-------|-------------|
| `pdfPipeline.runFull` | Run Full Pipeline | Execute all default stages (convert → clean → chunk → render) |
| `pdfPipeline.runConvert` | Convert Only | Run only the PDF → Markdown conversion stage |
| `pdfPipeline.runQA` | Generate QA Report | Generate a quality assurance report |
| `pdfPipeline.runDiff` | Compare Two Folders | Diff two output directories side-by-side |

## Analysis Commands

| Command | Title | Description |
|---------|-------|-------------|
| `pdfPipeline.runCrossRef` | Run Cross-Reference Analysis | Detect and resolve cross-references |
| `pdfPipeline.runAlgorithm` | Run Algorithm Extraction | Find pseudocode and algorithm blocks |
| `pdfPipeline.runNotation` | Run Notation Glossary | Catalog mathematical symbols and notation |
| `pdfPipeline.runSemanticChunk` | Run Semantic Chunking | ML-based semantic segmentation of sections |
| `pdfPipeline.runAllAnalysis` | Run All Analyses | Execute all four analysis modules |

## Preview & Dashboard

| Command | Title | Description |
|---------|-------|-------------|
| `pdfPipeline.previewFile` | Preview Markdown | Open a rendered preview of an output Markdown file |
| `pdfPipeline.refreshPreview` | Refresh Preview | Reload the Markdown preview panel |
| `pdfPipeline.refreshDashboard` | Refresh Dashboard | Reload the dashboard webview with latest stats |
| `pdfPipeline.refresh` | Refresh | Refresh the sidebar tree view |

## Context Menus

Commands are available in the sidebar tree view via right-click:

- **Session nodes** → Set as Active, Delete Session, Process Active Session
- **Action nodes** → Run Full Pipeline, Convert Only, QA Report, Diff, Open Config
- **Analysis nodes** → Individual analysis commands, Run All Analyses
- **Output nodes** → Preview, Reveal in Explorer, Delete
