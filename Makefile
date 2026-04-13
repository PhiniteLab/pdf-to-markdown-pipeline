.PHONY: all convert clean chunk render analyze validate lint format typecheck test docker-build clean-outputs help

PYTHON ?= python
CONFIG ?= configs/pipeline.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

all: ## Run the full pipeline (convert → clean → chunk → render)
	$(PYTHON) -m phinitelab_pdf_pipeline.run_pipeline --config $(CONFIG)

convert: ## PDF → Markdown (docling + markitdown)
	$(PYTHON) -m phinitelab_pdf_pipeline.convert --config $(CONFIG)

clean: ## Clean raw Markdown
	$(PYTHON) -m phinitelab_pdf_pipeline.clean --config $(CONFIG)

chunk: ## Split cleaned Markdown into chunks
	$(PYTHON) -m phinitelab_pdf_pipeline.chunk --config $(CONFIG)

render: ## Populate course templates
	$(PYTHON) -m phinitelab_pdf_pipeline.render_templates --config $(CONFIG)

analyze: ## Run analysis modules (semantic chunk, cross-ref, algorithm, notation)
	$(PYTHON) -m phinitelab_pdf_pipeline.run_pipeline --config $(CONFIG) --stages analyze

validate: ## Run validation modules (formula, scientific QA, citation context)
	$(PYTHON) -m phinitelab_pdf_pipeline.run_pipeline --config $(CONFIG) --stages validate

lint: ## Run ruff linter + formatter check
	$(PYTHON) -m ruff check phinitelab_pdf_pipeline/ tests/
	$(PYTHON) -m ruff format --check phinitelab_pdf_pipeline/ tests/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format phinitelab_pdf_pipeline/ tests/
	$(PYTHON) -m ruff check --fix phinitelab_pdf_pipeline/ tests/

typecheck: ## Run pyright type checker
	$(PYTHON) -m pyright phinitelab_pdf_pipeline/

test: ## Run tests with pytest + coverage
	$(PYTHON) -m pytest tests/ -v

docker-build: ## Build Docker image
	docker build -t phinitelab-pdf-pipeline .

clean-outputs: ## Remove all generated outputs (use with caution)
	rm -rf outputs/raw_md outputs/cleaned_md outputs/chunks outputs/quality outputs/.manifest.json
