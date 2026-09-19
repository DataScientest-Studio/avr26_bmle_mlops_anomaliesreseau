"""Ré-entraînement automatisé du modèle d'anomalies éCO2mix.

    ingest → build_raw → train

Découpage volontairement minimal : trois tâches, aucun PythonOperator.

Pourquoi ni tâche de promotion ni tâche de publication ? Parce que le code
applicatif s'en charge déjà, et qu'un second arbitre créerait deux sources de
vérité :

* ``src/models/mlflow_utils.log_training_run`` enregistre le run, crée une
  nouvelle version au Model Registry et appelle ``_promote_if_better``, qui
  pose l'alias ``champion`` si la MAE de validation est la plus basse ;
* ``src/models/predict_model.resolve_artifact`` sert ce champion depuis le
  Registry, avec repli sur ``models/model.joblib`` si MLflow est indisponible.

La promotion se fait donc en déplaçant un alias, pas en copiant un fichier.
Airflow orchestre la séquence et sa périodicité ; le code métier décide.

Tout le calcul tourne dans l'image applicative (``eco2mix-api``) via
DockerOperator. L'image Airflow reste minimale et n'embarque aucune dépendance
ML — polars, scikit-learn et numpy 2.x entreraient en conflit avec les
contraintes d'Airflow.

Simulation de l'arrivée de données : ``split_data_per_year`` lit le curseur
``src/data/max_year.conf``, filtre le CSV complet jusqu'à cette année, puis
incrémente le curseur. Chaque exécution du DAG apporte donc une année de plus,
et la MAE doit s'améliorer run après run dans MLflow.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

# --- contrat avec le reste de l'équipe, paramétrable par le .env -----------
TRAINER_IMAGE = os.environ.get("TRAINER_IMAGE", "eco2mix-api")
APP_NETWORK = os.environ.get("APP_NETWORK", "eco2mix_default")
MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")

# Chemin du projet SUR L'HÔTE. Les binds d'un DockerOperator sont interprétés
# par le démon Docker de la machine, pas par le conteneur Airflow : un chemin
# en /opt/airflow/... donnerait des montages vides, sans message d'erreur.
# Renseigné par `make airflow-prep-env`.
PROJECT_DIR = os.environ["PROJECT_DIR"]

TASK_ENV = {
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": os.environ.get("POSTGRES_DB", "eco2mix"),
    "POSTGRES_USER": os.environ.get("POSTGRES_USER", ""),
    "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
    "MLFLOW_TRACKING_URI": MLFLOW_URI,
    # Préfixe ANOM_ : voir src/config/config.py. Force la lecture depuis la
    # base plutôt que depuis le CSV national.
    "ANOM_SOURCE": "db",
    # MLflow cherche le SHA du dépôt pour taguer le run ; git n'est pas dans
    # l'image, ce qui produit trois avertissements par exécution.
    "GIT_PYTHON_REFRESH": "quiet",
    "PYTHONUNBUFFERED": "1",
}

TASK_MOUNTS = [
    # Zone servie à l'API : repli joblib si MLflow est indisponible.
    Mount(source=f"{PROJECT_DIR}/models", target="/app/models", type="bind"),
    # Métadonnées d'entraînement écrites par train_model.
    Mount(source=f"{PROJECT_DIR}/logs", target="/app/logs", type="bind"),
    # CSV complet dans data/raw/full/, CSV filtré dans data/raw/.
    Mount(source=f"{PROJECT_DIR}/data", target="/app/data", type="bind"),
    # max_year.conf est l'ÉTAT du curseur d'années. Il doit survivre aux
    # conteneurs jetables, sinon chaque exécution repartirait de la valeur
    # figée dans l'image. D'où ce montage de code par-dessus du code.
    Mount(source=f"{PROJECT_DIR}/src/data", target="/app/src/data", type="bind"),
]

DOCKER_DEFAULTS = dict(
    image=TRAINER_IMAGE,
    docker_url="unix://var/run/docker.sock",
    network_mode=APP_NETWORK,
    auto_remove="success",
    mount_tmp_dir=False,
    mounts=TASK_MOUNTS,
    environment=TASK_ENV,
)

default_args = {
    "owner": "equipe-mlops",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="retrain_eco2mix",
    description="Ingestion éCO2mix puis ré-entraînement et versioning MLflow",
    default_args=default_args,
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    schedule="0 4 * * *",          # tous les jours à 4h, heure de Paris
    catchup=False,
    max_active_runs=1,             # le curseur d'années n'est pas concurrent
    tags=["eco2mix", "mlops", "mlflow"],
) as dag:

    # 1. Une année de plus dans le CSV filtré, puis COPY vers staging.
    #    Les deux étapes partagent un conteneur : le fichier produit par la
    #    première est consommé par la seconde.
    ingest = DockerOperator(
        task_id="ingest",
        command=(
            "sh -c 'python -m src.data.split_data_per_year "
            "&& python -m src.data.load'"
        ),
        **DOCKER_DEFAULTS,
    )

    # 2. Typage staging → raw.eco2mix_national (TRUNCATE puis INSERT).
    build_raw = DockerOperator(
        task_id="build_raw",
        command="python -m src.data.build_raw",
        **DOCKER_DEFAULTS,
    )

    # 3. Entraînement depuis la base. Le script logue lui-même dans MLflow,
    #    crée une version au Registry et pose l'alias champion s'il gagne.
    train = DockerOperator(
        task_id="train",
        command="python -m src.models.train_model --model hgb",
        execution_timeout=timedelta(hours=2),
        **DOCKER_DEFAULTS,
    )

    ingest >> build_raw >> train
