.DEFAULT_GOAL := help

UV       ?= uv
NPM      ?= npm
BACKEND  := backend
FRONTEND := frontend
DEV_DATABASE_PORT ?= 55432
DEV_DATABASE_URL  ?= postgresql+psycopg://postgres:postgres@127.0.0.1:$(DEV_DATABASE_PORT)/whereabouts_hamburg

.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend up \
        build test test-backend lint lint-backend lint-frontend format clean \
        promote-admin-dev promote-admin-prd

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

up: ## Update and restart the live Docker Compose application
	docker compose up -d --build

promote-admin-dev: ## Promote a development Account: make promote-admin-dev USERNAME=name
	@test -n "$(USERNAME)" || (echo "USERNAME is required, for example: make promote-admin-dev USERNAME=david" >&2; exit 2)
	cd $(BACKEND) && DATABASE_URL="$(DEV_DATABASE_URL)" $(UV) run python admin_cli.py promote "$(USERNAME)"

promote-admin-prd: ## Promote a production Account: make promote-admin-prd USERNAME=name
	@test -n "$(USERNAME)" || (echo "USERNAME is required, for example: make promote-admin-prd USERNAME=david" >&2; exit 2)
	docker compose exec -T app uv run python admin_cli.py promote "$(USERNAME)"

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
