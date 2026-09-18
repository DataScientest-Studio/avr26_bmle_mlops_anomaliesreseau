#!/usr/bin/env bash
# Démarre le serveur MLflow : crée la base 'mlflow' si absente, puis lance le
# serveur avec back-end PostgreSQL et store d'artefacts local.
set -euo pipefail

pip install --no-cache-dir psycopg2-binary >/dev/null

python - <<'PY'
import os, psycopg2
u, p = os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"]
conn = psycopg2.connect(host="db", user=u, password=p, dbname="postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname='mlflow'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE mlflow")
    print("Base 'mlflow' créée.")
PY

exec mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri "postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/mlflow" \
  --artifacts-destination /mlartifacts --serve-artifacts
