# Version alignée sur le client installé par le projet (pyproject : mlflow>=3.1,
# résolu en 3.16.1 dans uv.lock). Le serveur et le client DOIVENT partager la
# même version majeure de schéma : un client récent enregistre un modèle via une
# source `models:/m-<model_id>` que l'ancien serveur 3.1.0 ne sait pas résoudre
# (il l'interprète comme un chemin local `./mlruns`, d'où un HTTP 500).
FROM ghcr.io/mlflow/mlflow:v3.16.1

# psycopg2 et boto3 ne sont pas dans l'image officielle. Les installer ici
# plutôt qu'au démarrage : plus rapide, reproductible, et fonctionne sans réseau.
#   - psycopg2-binary : backend store PostgreSQL
#   - boto3           : artefacts sur stockage objet S3 (MinIO)
RUN pip install --no-cache-dir \
      "psycopg2-binary>=2.9" \
      "boto3>=1.34"

# Utilisateur dédié : le serveur n'a rien à écrire en local
# (backend PostgreSQL, artefacts sur Silo via --serve-artifacts).
RUN useradd -m -u 1000 mlflow
USER mlflow
