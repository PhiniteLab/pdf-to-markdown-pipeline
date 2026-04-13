# Changelog

This file follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- English documentation for README, CONTRIBUTING, and CHANGELOG
- Development extras under `[project.optional-dependencies].dev` for pytest, pytest-cov, Ruff, Pyright, and pre-commit
- GitHub project links in `[project.urls]`
- `py.typed` package data in `[tool.setuptools.package-data]`
- A troubleshooting table in the README
- Pyright standard mode with 0 errors
- Coverage enforcement with a 70% minimum threshold
- Pre-commit hooks for Ruff and Pyright
- Parser and CLI tests for `run_pipeline`

### Changed
- Modernized `pyproject.toml` with readme, PEP 639 license metadata, authors, and classifiers
- Upgraded `pyrightconfig.json` from basic to standard mode
- Reduced `requirements.txt` to runtime dependencies only, with development dependencies moved under `[dev]`
- Updated the Dockerfile to install the package through `pip install .`
- Rewrote `README.md` with installation, CLI usage, project structure, troubleshooting, coverage, and pre-commit guidance
- Standardized repository-facing documentation to English
- Switched the default template rendering language in `configs/pipeline.yaml` to English

### Fixed
- `convert.py`: resolved the `BaseTableStructureOptions.mode` attribute issue by constructing `TableStructureOptions` directly
- `parallel.py`: added the `_get_pool` return type and a concrete type for the `futures` dictionary

### Removed
- Unused module-level constants: `HEADING_RE` in `chunk.py`, `BALANCED_PARENS_RE` in `formula_score.py`, `TABLE_ROW_RE` in `qa_pipeline.py`, and `SECTION_HEADING_RE` in `render_templates.py`
- The stale `pdf_to_markdown_pipeline.egg-info/` directory

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
