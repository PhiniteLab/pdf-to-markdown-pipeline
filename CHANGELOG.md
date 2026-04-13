# Changelog

This file follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Infrastructure & DevOps
- **CI/CD**: Rewrote `.github/workflows/ci.yml` with 5 parallel jobs — lint (ruff), typecheck (pyright), test (matrix Python 3.11/3.12/3.13 with coverage upload on 3.12 push), ts-build (Node 20, tsc --noEmit), docker (build verification)
- **Makefile**: Added `analyze`, `validate`, `typecheck`, `docker-build` targets (12 total)
- **Docker**: Non-root `pipeline` user (uid/gid 1000), `HEALTHCHECK`, `restart: "no"` policy
- **docker-compose**: New `analyze` service with profile-based `test` and `lint` services
- **GitHub community files**: `SECURITY.md`, issue templates (bug report, feature request), PR template

### Changed
- Test coverage increased from 74.83% → 81.11% (969 tests, 0 failures)
- Docker image hardened with non-root user and health check
- Makefile expanded from 8 to 12 targets

### Added

#### Phase 4: Quality & Integration Hardening
- **`formula_validate.py`**: Enhanced LaTeX formula validation — balanced delimiter checking (braces, brackets, parentheses with escape handling), \begin{}/\end{} environment matching, inline ($...$) vs display ($$...$$) math classification, standard LaTeX command validation against 80+ known commands and 20 known environments, nesting depth computation, weighted complexity scoring (0–100), and error/warning issue collection
- `FormulaIssue`, `Formula`, `FileValidation`, `ValidationSummary` dataclasses with `error_count`/`warning_count` properties
- `validate_formula()`, `extract_and_validate()`, `validate_file()`, `validate_tree()`, `build_summary()`, `write_report()` functions with JSON output
- **`citation_context.py`**: Citation context extraction and classification — surrounding sentence extraction for each citation, purpose classification into 7 categories (foundational, comparative, methodological, extending, background, refuting, unknown) using 18 linguistic cue patterns, author-year and numeric bracket citation detection, co-citation analysis (sentence-level pair counting), self-citation detection via document author surname overlap
- `CitationContext`, `CoCitation`, `SelfCitation`, `FileContextReport`, `ContextSummary` dataclasses
- `classify_purpose()`, `extract_citation_contexts()`, `detect_co_citations()`, `detect_self_citations()`, `analyze_file()`, `analyze_tree()`, `build_summary()`, `write_report()` functions
- **`scientific_qa.py`**: Scientific document quality assurance checks — theorem-proof pairing (with "proof omitted"/"left to reader" detection), definition-before-use, notation consistency (conflicting symbol definitions), cross-reference completeness, algorithm validity (input/output declarations, minimum body length), formula quality gate (fidelity scoring, empty block detection)
- `SciQAIssue`, `FileSciQAReport`, `SciQASummary` dataclasses with `badge` property (gold/silver/bronze/fail)
- `run_all_checks()` composite, `analyze_file()`, `analyze_tree()`, `build_summary()`, `write_report()` functions
- **Pipeline integration**: `run_pipeline.py` stages expanded from 4 to 6 — new `analyze` stage (semantic chunking, cross-reference analysis, algorithm extraction, notation glossary) and `validate` stage (formula validation, scientific QA, citation context), both optional (not in default stage list)
- CLI entry points for all three Phase 4 modules with `--input`, `--output`, `--config` options
- 139 new tests covering formula validation (delimiter checking, environment matching, command detection, nesting depth, complexity scoring, extraction, file/tree operations), citation context (sentence splitting, purpose classification for all 7 categories, context extraction, co-citation detection, self-citation detection, author extraction), scientific QA (theorem-proof pairing, definition-before-use, notation consistency, crossref completeness, algorithm validity, formula quality, badges, composite checks), and run_pipeline integration (stage choices, defaults)
- **`previewPanel.ts`**: Markdown preview WebView panel — renders converted output with syntax highlighting, math formula display ($$...$$ and $...$), QA badge overlay (GOLD/SILVER/BRONZE/FAIL), and content statistics toolbar (theorem/proof/definition/algorithm/formula/figure counts)
- **`dashboardPanel.ts`**: Dashboard WebView sidebar panel — displays pipeline overview (input PDF count, output file count), quality metrics (average score, badge distribution with progress bar), cross-reference stats (definitions, mentions, resolution rate), algorithm stats (count, avg steps, max depth), notation stats (unique symbols, entries, source counts)
- **Progress visualization**: `pipelineRunner.ts` now wraps all commands in `vscode.window.withProgress()` with notification-style progress bar, percentage extraction from output lines, cancellation support via `SIGTERM`
- **Analysis module commands**: 5 new VS Code commands — `runCrossRef`, `runAlgorithm`, `runNotation`, `runSemanticChunk`, `runAllAnalysis` — with corresponding tree actions and menu items
- **Preview command**: `previewFile` command opens any Markdown output file in a side-by-side WebView with rendered content, toolbar stats, and QA badge if available
- **Enhanced tree view**: New "Analysis" group with beaker icon in the sidebar tree, containing all 5 analysis actions (Cross References, Algorithm Extraction, Notation Glossary, Semantic Chunking, Run All)
- **Enhanced chat**: 7 new chat commands — `/crossref`, `/algorithm`, `/notation`, `/chunk`, `/analyze`, `/preview`, plus Turkish aliases (`çapraz referans`, `algoritma`, `notasyon`, `bölümleme`, `analiz`, `önizleme`)
- **Dashboard & Chat views registered**: `pdfPipelineDashboard` and `pdfPipelineChat` registered as webview sidebar panels in `package.json`
- 71 new tests covering VS Code extension file structure, package.json validation (views, commands, menus, configuration), TypeScript source patterns (imports, class names, method signatures), and cross-file consistency checks

### Changed
- VS Code extension version bumped from 0.2.0 → 0.3.0
- `chatView.ts` refactored to decouple from `SessionManager`/`PipelineRunner` — now delegates all operations via `vscode.commands.executeCommand()`
- `pipelineRunner.ts` `runPipeline()` now uses progress-wrapped execution
- `extension.ts` `refresh` command now also refreshes dashboard panel
- `cmdRunQA` now refreshes dashboard after QA report generation

#### Phase 2: Deep Analysis Modules (previously released)
- **`cross_ref.py`**: Cross-reference resolution and linking for scientific Markdown — detects definition sites (Theorem, Figure, Table, Equation labels), finds mentions in text, resolves references with kind normalization (Eq.→Equation, Fig.→Figure), computes resolution rate, and identifies unresolved references
- `RefDefinition`, `RefMention`, `CrossRefReport` dataclasses with category classification (theorem, equation, figure, table, section, algorithm)
- `analyze_file()` / `analyze_tree()` for file and directory-level cross-ref analysis with JSON report output
- **`algorithm_extract.py`**: Algorithm and pseudocode extraction module — detects fenced code blocks and "Algorithm N" header lines, parses inputs/outputs/steps with indentation-based nesting, identifies control flow keywords (for, while, if, return, else, repeat, until)
- `Algorithm`, `AlgoStep` dataclasses with `step_count`, `max_depth`, `full_label` properties
- `is_algorithm_content()` keyword threshold check for distinguishing pseudocode from regular code
- **`notation_glossary.py`**: Mathematical notation glossary builder — extracts explicit definitions (Let/is/where/define-as patterns), list notations (`- $X$: desc`), table notations (`| $X$ | desc |`), and detects 50+ common LaTeX symbols (\\alpha, \\nabla, \\sum, etc.)
- `NotationEntry`, `NotationGlossary` dataclasses with `unique_symbols`, `lookup()`, `deduplicated()` methods
- Markdown glossary export (`write_markdown_glossary()`) and JSON report output
- CLI entry points for all three Phase 2 modules with `--input`, `--output`, `--config` options
- 66 new tests covering cross-reference resolution, algorithm extraction, notation glossary building, file/tree operations, and report generation
- **`semantic_chunk.py`**: New module for scientific-aware chunking — recognises Theorem, Proof, Definition, Lemma, Proposition, Corollary, Example, Remark, Algorithm blocks with entity labels, QED detection, formula extraction, and cross-reference parsing
- `SemanticChunk` dataclass with `entity_type`, `entity_label`, `entity_name`, `parent_label`, `formulas`, `cross_refs` fields
- Proof–theorem parent linking (proof blocks auto-link to preceding theorem)
- Algorithm detection via both code fences and `Algorithm N.M` label lines
- `chunks_to_records()` and `build_entity_summary()` helper functions for downstream export
- CLI entry point for `semantic_chunk.py` with `--input`, `--output-dir`, `--config`, `--no-manifest`
- 44 new tests covering all semantic chunk parsing, rendering, file/tree operations, formula extraction, cross-ref extraction, QED detection, regex patterns, and entity summary
- RAG export semantic enrichment: `entity_type`, `entity_label`, `formulas`, `cross_refs` now included in chunk metadata
- `build_summary()` in `rag_export.py` now reports `entity_types` distribution and `total_formulas` count
- 7 new RAG enrichment tests for theorem/definition/cross-ref detection in chunks and summary statistics
- Comprehensive Features section in README covering all 20+ modules
- Detailed analysis modules table with output descriptions
- Full CLI examples (sessions, custom input, no-manifest) in README
- `data/raw/` subdirectory listing in project structure
- VS Code extension file details in project structure
- CI workflow reference in project structure
- "Adding a New Module" guide in CONTRIBUTING.md
- Plugin directory convention note in CONTRIBUTING.md

### Changed
- Corrected all GitHub URLs from `phinitelab-pdf-pipeline` to `pdf-to-markdown-pipeline` (repo name) across pyproject.toml, README.md, and CONTRIBUTING.md
- Expanded pipeline flow diagram with box-style visualization
- Updated configuration example to reflect complete `pipeline.yaml` (device: auto, markitdown.enabled, max_repeated_header_length, render_templates options, logging format/date_format)
- Developer installation in CONTRIBUTING.md now includes CPU torch pre-install step
- Updated Pyright status to "0 errors, 0 warnings" (was "0 errors")
- Refreshed VS Code extension README with session management, tree view, and settings documentation
- Expanded CHANGELOG with full module-level detail

### Fixed
- `plugin.py`: suppressed spurious Pyright `reportUnnecessaryIsInstance` warning on `register()` method
- GitHub CI badge and all `git clone` / `pip install git+` URLs now point to the correct repository

## [0.1.0] - 2026-04-12

### Added
- Initial release of the PDF → Markdown pipeline
- Docling + markitdown dual-engine conversion support
- Cleaning, chunking, and template rendering stages
- SHA-256 manifest support for idempotent execution
- Parallel processing helpers
- QA pipeline, metadata extraction, citation graphing, and formula scoring
- OCR quality checks, figure cataloging, and topic classification
- Version diffing and document type detection
- RAG-oriented export, multi-format output, and GitHub Pages generation
- Plugin architecture
- Test coverage for the initial release baseline
- GitHub Actions CI, Docker support, and Makefile shortcuts
