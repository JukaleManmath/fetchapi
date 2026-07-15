.PHONY: lint format format-check typecheck test test-unit test-integration \
        check migrate migrate-create run install install-dev \
        up down logs ps build db-shell reset-db

BACKEND := backend
COMPOSE  := docker compose -f infra/compose.yaml
PYTHON   := $(BACKEND)/.venv/bin/python

# ── Installation ──────────────────────────────────────────────────────────────

venv:
	python3 -m venv $(BACKEND)/.venv

install: venv
	$(PYTHON) -m pip install -e $(BACKEND)

install-dev: venv
	$(PYTHON) -m pip install -e "$(BACKEND)[dev]"

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	$(PYTHON) -m ruff check $(BACKEND)

format:
	$(PYTHON) -m ruff format $(BACKEND)

format-check:
	$(PYTHON) -m ruff format --check $(BACKEND)

typecheck:
	$(PYTHON) -m mypy $(BACKEND)/src

check: lint format-check typecheck

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest $(BACKEND)/tests

test-unit:
	$(PYTHON) -m pytest $(BACKEND)/tests/unit

test-integration:
	$(PYTHON) -m pytest $(BACKEND)/tests/integration -m integration

test-cov:
	$(PYTHON) -m pytest $(BACKEND)/tests --cov=$(BACKEND)/src/fetch --cov-report=term-missing

# ── Database ──────────────────────────────────────────────────────────────────

migrate:
	cd $(BACKEND) && ../.venv/bin/alembic upgrade head 2>/dev/null || $(PYTHON) -m alembic upgrade head

# Usage: make migrate-create name="add_sources_table"
migrate-create:
	cd $(BACKEND) && $(PYTHON) -m alembic revision --autogenerate -m "$(name)"

migrate-down:
	cd $(BACKEND) && $(PYTHON) -m alembic downgrade -1

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	cd $(BACKEND) && $(CURDIR)/$(BACKEND)/.venv/bin/uvicorn fetch.main:app --reload --host 0.0.0.0 --port 8000

# ── Docker ────────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

db-shell:
	$(COMPOSE) exec postgres psql -U fetchapi -d fetchapi

# Wipes all volumes and restarts from scratch — destructive, use with care
reset-db:
	$(COMPOSE) down -v
	$(COMPOSE) up -d postgres
	$(COMPOSE) exec postgres pg_isready -U fetchapi
