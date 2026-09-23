#!/bin/sh
# Initialisation du stockage objet Silo pour MLflow.
# Idempotent : peut être relancé à chaque démarrage.
set -eu

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER manquant}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD manquant}"
: "${SILO_MLFLOW_ACCESS_KEY:?SILO_MLFLOW_ACCESS_KEY manquant}"
: "${SILO_MLFLOW_SECRET_KEY:?SILO_MLFLOW_SECRET_KEY manquant}"

BUCKET=mlflow
POLICY=mlflow-rw

# Alias d'administration, défini par variable d'environnement :
# les identifiants root ne sont jamais écrits sur disque.
export MC_HOST_silo="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@silo:9000"

echo "[init] Bucket ${BUCKET}"
mcli mb --ignore-existing "silo/${BUCKET}"

echo "[init] Politique ${POLICY}"
mcli admin policy create silo "${POLICY}" /init/mlflow-policy.json

echo "[init] Utilisateur applicatif ${SILO_MLFLOW_ACCESS_KEY}"
mcli admin user add silo "${SILO_MLFLOW_ACCESS_KEY}" "${SILO_MLFLOW_SECRET_KEY}"

echo "[init] Attachement de la politique"
mcli admin policy attach silo "${POLICY}" --user "${SILO_MLFLOW_ACCESS_KEY}" \
  || echo "[init] Politique déjà attachée"

echo "[init] Terminé"
