#!/usr/bin/env bash
# Démarre le serveur MLflow. La base et le rôle 'mlflow' sont créés en amont
# par `make db-meta` : ce script ne se connecte jamais en superutilisateur.
set -euo pipefail

pip install --no-cache-dir psycopg2-binary >/dev/null

exec mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri "postgresql+psycopg2://mlflow:${MLFLOW_DB_PASSWORD}@db:5432/mlflow" \
  --artifacts-destination /mlartifacts --serve-artifacts
