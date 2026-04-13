# Contributing Guide

If you want to contribute to this project, follow the steps below.

## Development Environment

```bash
git clone https://github.com/PhiniteLab/pdf-to-markdown-pipeline.git
cd pdf-to-markdown-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
```

## Code Standards

- **Formatting**: [Ruff](https://docs.astral.sh/ruff/) with a line length of 120
- **Linting**: Ruff rules `E`, `F`, `W`, `I`, `UP`, `B`, `SIM`, and `RUF`
- **Type checking**: [Pyright](https://github.com/microsoft/pyright) in standard mode
- **Python**: 3.11+ with `from __future__ import annotations`

Checks to run before committing:

```bash
make lint          # Lint and formatting checks
make test          # 429 tests
pyright phinitelab_pdf_pipeline/   # Type checking (0 errors, 0 warnings)
pre-commit run --all-files
```

## Pull Request Process

1. Create a branch from `main`, for example `git checkout -b feature/short-description`.
2. Implement your changes and add or update tests.
3. Make sure all checks pass: `make lint && make test && pyright phinitelab_pdf_pipeline/`.
4. Write a clear commit message.
5. Open a pull request and describe what changed and why.

## Writing Tests

- The main test suite lives in `tests/test_pipeline_structure.py`.
- Add tests for each new function or behavior change.
- Use the `tmp_path` fixture for filesystem-based tests.
- Minimum coverage threshold is **70%** (enforced by pytest-cov).

```bash
# Run a single test pattern
python -m pytest tests/ -k "test_name" -v
```

## Project Structure Rules

- All pipeline modules live under the `phinitelab_pdf_pipeline/` package.
- Each module should remain executable through its own `main()` function and CLI arguments where appropriate.
- Shared helpers belong in `phinitelab_pdf_pipeline/common.py`.
- Configuration is loaded from `configs/pipeline.yaml` through `load_config()`.
- Plugin extensions are placed in a `plugins/` directory and auto-discovered by the `PluginRegistry`.

## Adding a New Module

1. Create the module file in `phinitelab_pdf_pipeline/`.
2. Include a `main()` function with `argparse` for standalone execution.
3. Add corresponding tests in `tests/test_pipeline_structure.py`.
4. Update `configs/pipeline.yaml` if the module needs configuration.
5. Run `make lint && make test && pyright phinitelab_pdf_pipeline/` to verify.

## Reporting Issues

[GitHub Issues](https://github.com/PhiniteLab/pdf-to-markdown-pipeline/issues) is the preferred place to report problems. When filing an issue, include:

- Your Python version
- The full error output or traceback
- The config file you used, if it does not contain sensitive data
