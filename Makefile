.PHONY: up down build restart logs psql sync lock lint test init new_data reset \
        train predict evaluate snapshot \
        db-meta airflow-prep-env airflow-build airflow airflow-down \
        airflow-logs airflow-shell airflow-reset mlflow mlflow-build mlflow-down mlflow-logs mlflow-champion
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

restart: down build up

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

test-v: ### Teste avec détails et temps d'exécutionuv run python -m src.models.train_model
	uv run pytest -v --durations=10

init:
	uv run alembic upgrade head && uv run python -m src.data.load && uv run python -m src.data.build_raw && uv run python -m src.data.create_users

new_data:
	uv run python -m src.data.split_data_per_year && uv run python -m src.data.load && uv run python -m src.data.build_raw

reset:
	uv run python -m src.data.reset_last_year

# --- Modèle : entraînement, prédiction, versioning (partie modèle) ---------
train: ## Entraîne le modèle + logue le run dans MLflow (promotion champion)
	uv run python -m src.models.train_model

predict: ## Score la source configurée -> data/processed/predictions.parquet
	uv run python -m src.models.predict_model --save

evaluate: ## Évalue le modèle
	uv run python -m src.models.evaluate

snapshot: ## Fige un instantané daté du dataset (reference data)
	uv run python -m src.data.snapshot

db-meta: ## Crée les rôles et bases de métadonnées
	docker compose up -d db
	@docker compose exec -T db psql -U eco2mix -d eco2mix -v ON_ERROR_STOP=1 \
		-v mlflow_pwd="$(MLFLOW_DB_PASSWORD)" \
		-v airflow_pwd="$(AIRFLOW_DB_PASSWORD)" \
		-f - < db/init/01-create-databases.sql

airflow-prep-env: ## Génère les variables dépendantes de la machine (macOS + Linux)
	@tmp=$$(mktemp); \
	grep -vE '^(DOCKER_SOCK|AIRFLOW_UID|DOCKER_GID|AIRFLOW_FERNET_KEY|PROJECT_DIR)=$$' .env > "$$tmp" \
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
	grep -qE '^PROJECT_DIR=.+'        .env || echo "PROJECT_DIR=$$(pwd)" >> .env; \
	grep -qE '^AIRFLOW_FERNET_KEY=.+' .env || echo "AIRFLOW_FERNET_KEY=$$(docker run --rm python:3.12-slim sh -c "pip -q install --root-user-action=ignore cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")" >> .env
	@echo "--- variables machine ---"
	@grep -E '^(DOCKER_SOCK|AIRFLOW_UID|DOCKER_GID|PROJECT_DIR|AIRFLOW_FERNET_KEY)=' .env | sed -E 's/(FERNET_KEY)=.*/\1=********/'

airflow-build: ## Construit l'image Airflow
	docker compose --profile airflow build

airflow: ## Démarre la stack Airflow (init + webserver + scheduler)
	@[ "$(PROJECT_DIR)" = "$$(pwd)" ] || { echo "PROJECT_DIR obsolète — relancez make airflow-prep-env"; exit 1; }
	mkdir -p dags logs/airflow plugins models models_staging
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

mlflow-build: ## construit l'image, sans démarrer
	docker compose build mlflow

mlflow: ## Démarre MLflow seul et affiche l'URL
	docker compose up -d mlflow
	@echo "Interface : http://localhost:$(MLFLOW_PORT)"

mlflow-down: ## Arrête mlflow
	docker compose down mlflow

mlflow-logs: ## Suit les logs du serveur MLflow
	docker compose logs -f mlflow

mlflow-champion: ## Affiche la version du modèle portant l'alias champion
	@docker compose exec -T db psql -U $(POSTGRES_USER) -d mlflow -t -A -F' | ' \
		-c "SELECT name, alias, version FROM registered_model_aliases;"

silo-prep-env: ## Génère les secrets Silo manquants dans .env (n'écrase rien)
	@tmp=$$(mktemp); \
	grep -vE '^(SILO_ROOT_USER|SILO_ROOT_PASSWORD|SILO_MLFLOW_ACCESS_KEY|SILO_MLFLOW_SECRET_KEY)=$$' .env > "$$tmp" \
	  && mv "$$tmp" .env
	@[ -s .env ] && [ -n "$$(tail -c1 .env)" ] && printf '\n' >> .env || true
	@grep -qE '^SILO_ROOT_USER=.+'         .env || echo "SILO_ROOT_USER=silo-admin"                          >> .env
	@grep -qE '^SILO_ROOT_PASSWORD=.+'     .env || echo "SILO_ROOT_PASSWORD=$$(openssl rand -hex 24)"         >> .env
	@grep -qE '^SILO_MLFLOW_ACCESS_KEY=.+' .env || echo "SILO_MLFLOW_ACCESS_KEY=mlflow-app"                   >> .env
	@grep -qE '^SILO_MLFLOW_SECRET_KEY=.+' .env || echo "SILO_MLFLOW_SECRET_KEY=$$(openssl rand -hex 24)"     >> .env
	@echo "--- variables Silo (secrets masqués) ---"
	@grep -E '^SILO_' .env | sed -E 's/(PASSWORD|SECRET_KEY)=.*/\1=********/'

silo-check: ## Vérifie que les variables Silo sont renseignées
	@for v in SILO_ROOT_USER SILO_ROOT_PASSWORD SILO_MLFLOW_ACCESS_KEY SILO_MLFLOW_SECRET_KEY; do \
	  [ -n "$$(printenv $$v)" ] || { echo "$$v vide — lancez : make silo-prep-env"; exit 1; }; \
	done

silo: silo-check ## Démarre Silo et initialise le bucket MLflow
	docker compose up -d silo silo-init
	@echo "Console : http://127.0.0.1:9001"

silo-init: silo-check ## Relance l'initialisation (bucket, politique, utilisateur)
	docker compose run --rm silo-init

silo-update: silo-check ## Met à jour Silo vers le dernier patch et rescanne l'image
	docker compose pull silo silo-init
	docker run --rm aquasec/trivy:latest image --severity HIGH,CRITICAL --scanners vuln pgsty/silo:latest
	docker compose up -d silo
	docker compose exec silo silo --version

silo-logs: ## Suit les logs de Silo
	docker compose logs -f silo
