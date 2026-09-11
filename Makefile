.PHONY: up down logs psql sync lock lint test

up:    ## Démarre Postgres
	docker compose up -d

down:  ## Arrête Postgres (conserve les données)
	docker compose down

logs:  ## Suit les logs de la base
	docker compose logs -f db

psql:  ## Ouvre un shell SQL
	docker compose exec db psql -U eco2mix -d eco2mix

sync:  ## Installe les dépendances
	uv sync

lock:  ## Régénère requirements.txt depuis uv.lock
	uv export --format requirements-txt --no-hashes --no-dev --no-emit-project -o requirements.txt

lint:
	uv run ruff check src tests

test:
	uv run pytest -q

init:
	uv run alembic upgrade head && uv run python -m src.data.load && uv run python -m src.data.build_raw
