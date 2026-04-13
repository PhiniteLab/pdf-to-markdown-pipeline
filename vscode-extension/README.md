# PDF Markdown Pipeline VS Code Extension (MVP)

This extension runs the existing Python pipeline commands from VS Code.

## Commands

- `PDF Pipeline: Run Full Pipeline`
- `PDF Pipeline: Convert Only`
- `PDF Pipeline: Generate QA Report`
- `PDF Pipeline: Compare Two Output Folders`
- `PDF Pipeline: Open Pipeline Config`

## Settings

- `pdfPipeline.pythonPath` (default: `python`)
- `pdfPipeline.configPath` (default: `configs/pipeline.yaml`)
- `pdfPipeline.defaultEngine` (`docling` | `markitdown` | `dual`)

## Development

```bash
cd vscode-extension
npm install
npm run compile
```

Press `F5` in VS Code to run the extension in an Extension Development Host.
