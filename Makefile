.PHONY: up down logs psql sync lock lint test
ifeq (,$(wildcard .env))
$(error .env absent — lancez d'abord : "cp .env.example .env")
endif
# Charge les variables du fichier .env dans le contexte de make
include .env
# Exporte toutes les variables (du .env + celles déjà définies) vers l'environnement
# des sous-processus, y compris docker compose
export

up:    ## Démarre Postgres + API
	docker compose up

down:  ## Arrête Postgres (conserve les données) + API
	docker compose down

build: ## Rebuild
	docker compose build

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
	uv run alembic upgrade head && uv run python -m src.data.load && uv run python -m src.data.build_raw && uv run python -m src.data.create_users

new_data:
	uv run python -m src.data.split_data_per_year && uv run python -m src.data.load && uv run python -m src.data.build_raw

reset:
	uv run python -m src.data.reset_last_year

db-meta: ## Crée les rôles et bases de métadonnées
	docker compose up -d db
	@docker compose exec -T db psql -U eco2mix -d eco2mix -v ON_ERROR_STOP=1 \
		-v mlflow_pwd="$(MLFLOW_DB_PASSWORD)" \
		-v airflow_pwd="$(AIRFLOW_DB_PASSWORD)" \
		-f - < db/init/01-create-databases.sql

airflow-prep-env: ## Génère les variables dépendantes de la machine (macOS + Linux)
	@tmp=$$(mktemp); \
	grep -vE '^(DOCKER_SOCK|AIRFLOW_UID|DOCKER_GID|AIRFLOW_FERNET_KEY)=$$' .env > "$$tmp" \
	  && mv "$$tmp" .env
	@[ -s .env ] && [ -n "$$(tail -c1 .env)" ] && printf '\n' >> .env || true
	@sock=$$(docker context inspect --format '{{.Endpoints.docker.Host}}' | sed 's|unix://||'); \
	case "$$(uname -s)" in \
	  Darwin) uid=50000; gid=0 ;; \
	  *)      uid=$$(id -u); gid=$$(stat -c '%g' "$$sock" 2>/dev/null || echo 0) ;; \
	esac; \
	grep -qE '^DOCKER_SOCK=.+'        .env || echo "DOCKER_SOCK=$$sock" >> .env; \
	grep -qE '^AIRFLOW_UID=.+'        .env || echo "AIRFLOW_UID=$$uid"  >> .env; \
	grep -qE '^DOCKER_GID=.+'         .env || echo "DOCKER_GID=$$gid"   >> .env; \
	grep -qE '^AIRFLOW_FERNET_KEY=.+' .env || echo "AIRFLOW_FERNET_KEY=$$(docker run --rm python:3.12-slim sh -c "pip -q install --root-user-action=ignore cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")" >> .env
	@echo "--- variables machine ---"
	@grep -E '^(DOCKER_SOCK|AIRFLOW_UID|DOCKER_GID|AIRFLOW_FERNET_KEY)=' .env

airflow-build: ## Construit l'image Airflow
	docker compose --profile airflow build

airflow: db-meta ## Démarre la stack Airflow (init + webserver + scheduler)
	mkdir -p dags logs/airflow plugins
	docker compose --profile airflow up -d
	@echo "Interface : http://localhost:$(AIRFLOW_PORT)"

airflow-down: ## Arrête Airflow, conserve les métadonnées
	docker compose --profile airflow down

airflow-logs: ## Suit les logs du scheduler
	docker compose logs -f airflow-scheduler

airflow-shell: ## Shell dans le scheduler
	docker compose exec airflow-scheduler bash

airflow-reset: ## Remet à zéro les métadonnées Airflow
	docker compose --profile airflow down
	docker compose exec -T db psql -U $(POSTGRES_USER) -d postgres -v ON_ERROR_STOP=1 \
		-c "DROP DATABASE IF EXISTS airflow;" \
		-c "CREATE DATABASE airflow OWNER airflow;"
	$(MAKE) airflow
