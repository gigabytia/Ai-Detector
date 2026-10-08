# Every target has a PowerShell equivalent in docs/development.md; make is optional.
.PHONY: install infra up down migrate seed api worker frontend test test-integration lint fmt api-types build check

install:
	uv sync
	npm --prefix frontend ci

infra:
	docker compose up -d postgres redis

up:
	docker compose up --build

down:
	docker compose down

migrate:
	uv run alembic -c backend/alembic.ini upgrade head

seed:
	uv run ai-detector-seed

api:
	uv run ai-detector-api

worker:
	uv run ai-detector-worker

frontend:
	npm --prefix frontend run dev

test:
	uv run pytest
	npm --prefix frontend test

test-integration: migrate
	uv run pytest -m integration

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy shared/src backend/src vision-worker/src tests
	npm --prefix frontend run lint
	npm --prefix frontend run format:check
	npm --prefix frontend run typecheck

fmt:
	uv run ruff check --fix .
	uv run ruff format .
	npm --prefix frontend run format

api-types:
	uv run ai-detector-openapi frontend/openapi.json
	npm --prefix frontend run api:types

build:
	npm --prefix frontend run build

check: lint test build
