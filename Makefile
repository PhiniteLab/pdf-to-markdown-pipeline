.PHONY: all convert clean chunk render lint test help

PYTHON ?= python
CONFIG ?= configs/pipeline.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

all: ## Run the full pipeline (convert → clean → chunk → render)
	$(PYTHON) -m scripts.run_pipeline --config $(CONFIG)

convert: ## PDF → Markdown (docling + markitdown)
	$(PYTHON) -m scripts.convert --config $(CONFIG)

clean: ## Clean raw Markdown
	$(PYTHON) -m scripts.clean --config $(CONFIG)

chunk: ## Split cleaned Markdown into chunks
	$(PYTHON) -m scripts.chunk --config $(CONFIG)

render: ## Populate course templates
	$(PYTHON) -m scripts.render_templates --config $(CONFIG)

lint: ## Run ruff linter + formatter check
	$(PYTHON) -m ruff check scripts/ tests/
	$(PYTHON) -m ruff format --check scripts/ tests/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format scripts/ tests/
	$(PYTHON) -m ruff check --fix scripts/ tests/

test: ## Run tests with pytest
	$(PYTHON) -m pytest tests/ -v

clean-outputs: ## Remove all generated outputs (use with caution)
	rm -rf outputs/raw_md outputs/cleaned_md outputs/chunks outputs/.manifest.json
