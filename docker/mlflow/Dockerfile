FROM ghcr.io/mlflow/mlflow:v3.1.0

# psycopg2 n'est pas dans l'image officielle. L'installer ici plutôt qu'au
# démarrage : plus rapide, reproductible, et fonctionne sans réseau.
RUN pip install --no-cache-dir "psycopg2-binary>=2.9"
