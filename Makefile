.PHONY: check lint test up down migrate seed

# Local dev quality gate (matches the CI backend job): lint + type-check + tests.
check: lint typecheck test

lint:
	cd backend && .venv/bin/ruff check app tests

typecheck:
	cd backend && .venv/bin/mypy app

test:
	cd backend && .venv/bin/python -m pytest -q

# Containerized stack (Postgres + Redis + API + worker + beat).
up:
	docker compose up --build

down:
	docker compose down

migrate:
	cd backend && .venv/bin/alembic upgrade head
