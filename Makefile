.DEFAULT_GOAL := help

UV       ?= uv
NPM      ?= npm
BACKEND  := backend
FRONTEND := frontend

.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend \
        build test test-backend lint lint-backend lint-frontend format clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install backend and frontend dependencies

install-backend: ## Install locked backend dependencies
	cd $(BACKEND) && $(UV) sync --locked

install-frontend: ## Install locked frontend dependencies
	cd $(FRONTEND) && $(NPM) ci

dev: ## Run backend and frontend together
	./scripts/dev.sh

dev-backend: ## Run the backend development server
	cd $(BACKEND) && $(UV) run uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run the frontend development server
	cd $(FRONTEND) && $(NPM) run dev -- --host 0.0.0.0 --port 5173

build: ## Build the production frontend
	cd $(FRONTEND) && $(NPM) run build

test: test-backend ## Run all tests

test-backend: ## Run backend tests
	cd $(BACKEND) && $(UV) run pytest -q

lint: lint-backend lint-frontend ## Lint backend and frontend

lint-backend: ## Lint backend Python
	cd $(BACKEND) && $(UV) run ruff check .

lint-frontend: ## Lint frontend TypeScript
	cd $(FRONTEND) && $(NPM) run lint

format: ## Format backend Python
	cd $(BACKEND) && $(UV) run ruff format .

clean: ## Remove generated artifacts and caches
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
