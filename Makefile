.PHONY: all convert clean chunk render analyze validate lint format typecheck test docker-build clean-outputs help

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then printf %s .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then command -v python3; else command -v python; fi)
CONFIG ?= configs/pipeline.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

all: ## Run the full pipeline (convert → clean → chunk → render)
	$(PYTHON) -m cortexmark.run_pipeline --config $(CONFIG)

convert: ## PDF → Markdown (docling + markitdown)
	$(PYTHON) -m cortexmark.convert --config $(CONFIG)

clean: ## Clean raw Markdown
	$(PYTHON) -m cortexmark.clean --config $(CONFIG)

chunk: ## Split cleaned Markdown into chunks
	$(PYTHON) -m cortexmark.chunk --config $(CONFIG)

render: ## Populate source templates
	$(PYTHON) -m cortexmark.render_templates --config $(CONFIG)

analyze: ## Run analysis modules (semantic chunk, cross-ref, algorithm, notation)
	$(PYTHON) -m cortexmark.run_pipeline --config $(CONFIG) --stages analyze

validate: ## Run validation modules (formula, scientific QA, citation context)
	$(PYTHON) -m cortexmark.run_pipeline --config $(CONFIG) --stages validate

lint: ## Run ruff linter + formatter check
	$(PYTHON) -m ruff check cortexmark/ tests/
	$(PYTHON) -m ruff format --check cortexmark/ tests/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format cortexmark/ tests/
	$(PYTHON) -m ruff check --fix cortexmark/ tests/

typecheck: ## Run pyright type checker
	$(PYTHON) -m pyright cortexmark/

test: ## Run tests with pytest + coverage
	$(PYTHON) -m pytest tests/ -v

docker-build: ## Build Docker image
	docker build -t cortexmark .

clean-outputs: ## Remove all generated outputs (use with caution)
	$(PYTHON) -c "from shutil import rmtree; from cortexmark.common import load_config, resolve_configured_path, resolve_manifest_path; cfg = load_config(); [rmtree(target, ignore_errors=True) for target in (resolve_configured_path(cfg, 'output_raw_md', 'outputs/raw_md'), resolve_configured_path(cfg, 'output_cleaned_md', 'outputs/cleaned_md'), resolve_configured_path(cfg, 'output_chunks', 'outputs/chunks'), resolve_configured_path(cfg, 'output_quality', 'outputs/quality'), resolve_configured_path(cfg, 'output_semantic_chunks', 'outputs/semantic_chunks'))]; manifest = resolve_manifest_path(cfg); manifest.exists() and manifest.unlink()"
