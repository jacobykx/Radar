# 2027 IAP Planning Module — developer entry points.
#
#   make setup     one-time install of both halves
#   make dev       what to run in two terminals
#   make check     everything CI runs
#
# Every target works on the native toolchain (Poetry + npm). The Docker targets are an
# alternative for a machine without them, or to reproduce a Postgres-only problem.

BACKEND  := backend
FRONTEND := frontend

# Override to point at Postgres, e.g.
#   make migrate DATABASE_URL=postgresql+psycopg://iap:iap_local_dev@127.0.0.1:5432/iap
#
# Exported only when set: an empty IAP_DATABASE_URL in the environment would take
# precedence over backend/.env and leave the application with no connection string.
DATABASE_URL ?=
ifneq ($(strip $(DATABASE_URL)),)
export IAP_DATABASE_URL = $(DATABASE_URL)
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend env dev dev-backend dev-frontend \
        migrate migration seed reset test test-backend test-frontend lint typecheck \
        build check generate-api docker-up docker-down docker-seed clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── setup ──────────────────────────────────────────────────────────────────────

setup: setup-backend setup-frontend env ## Install both halves and write backend/.env
	@echo "Setup complete. Next: make migrate && make seed, then make dev"

setup-backend: ## Install backend dependencies into backend/.venv
	cd $(BACKEND) && poetry config virtualenvs.in-project true --local && poetry install

setup-frontend: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

env: $(BACKEND)/.env ## Create backend/.env from the example if absent

$(BACKEND)/.env:
	cp $(BACKEND)/.env.example $(BACKEND)/.env
	@echo "Wrote $(BACKEND)/.env — IAP_AUTH_DEV_MODE=true is LOCAL ONLY."

# ── running ────────────────────────────────────────────────────────────────────

dev: ## Print the two commands to run
	@echo "Two terminals:"
	@echo "  make dev-backend    → http://127.0.0.1:8010 (docs at /docs)"
	@echo "  make dev-frontend   → http://127.0.0.1:3010"

dev-backend: ## Run the API with reload
	cd $(BACKEND) && .venv/bin/python -m uvicorn app.main:app --port 8010 --reload

dev-frontend: ## Run the Next dev server
	cd $(FRONTEND) && npm run dev

# ── database ───────────────────────────────────────────────────────────────────

migrate: ## Apply migrations up to head
	cd $(BACKEND) && .venv/bin/alembic upgrade head

migration: ## Autogenerate a revision: make migration M="add widget table"
	@test -n "$(M)" || (echo "Set M, e.g. make migration M=\"add widget table\"" && exit 1)
	cd $(BACKEND) && .venv/bin/alembic revision --autogenerate -m "$(M)"
	@echo "Review the generated file before committing — autogenerate is a draft."

seed: ## Migrate and load the synthetic fixtures
	cd $(BACKEND) && .venv/bin/python -m scripts.bootstrap

reset: ## Drop everything, re-migrate, re-seed
	cd $(BACKEND) && .venv/bin/python -m scripts.bootstrap --reset

# ── checks ─────────────────────────────────────────────────────────────────────

check: lint typecheck test build ## Everything CI runs

test: test-backend test-frontend ## Run both test suites

test-backend: ## pytest
	cd $(BACKEND) && .venv/bin/python -m pytest

test-frontend: ## jest
	cd $(FRONTEND) && npm test

lint: ## ruff
	cd $(BACKEND) && .venv/bin/ruff check .

typecheck: ## tsc
	cd $(FRONTEND) && npx tsc --noEmit

build: ## Production build of the frontend
	cd $(FRONTEND) && npm run build

generate-api: ## Regenerate the typed client (needs the backend running)
	cd $(FRONTEND) && npm run generate:api

# ── docker ─────────────────────────────────────────────────────────────────────

docker-up: ## Postgres + API + frontend in containers
	docker compose up --build

docker-down: ## Stop the stack and drop its volume
	docker compose down -v

docker-seed: ## Load fixtures into the containerised database
	docker compose run --rm seed

# ── housekeeping ───────────────────────────────────────────────────────────────

clean: ## Remove build artefacts, caches and the local SQLite database
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/.next
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f $(BACKEND)/*.db
