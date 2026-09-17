"""DAG de recette — valide l'environnement Airflow couche par couche.

À exécuter une fois, juste après `make airflow`. Chaque tâche isole un point de
défaillance précis, pour que l'échec dise immédiatement quoi corriger :

    bash   → le worker exécute du code
    python → les dépendances de l'image sont présentes
    db     → le réseau Compose relie Airflow à Postgres
    docker → le socket Docker est accessible (prérequis du DockerOperator)

Une fois les quatre au vert, l'environnement est bon. Le DAG peut rester en
place : schedule=None, il ne se déclenche jamais tout seul.
"""

from __future__ import annotations

import logging
import os

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator

logger = logging.getLogger(__name__)


def _check_env(**_) -> dict:
    """Couche 2 : l'image contient-elle ce qu'il faut ?"""
    import sys

    interesting = [
        "AIRFLOW__CORE__EXECUTOR",
        "AIRFLOW__CORE__DEFAULT_TIMEZONE",
        "PYTHONUNBUFFERED",
    ]
    found = {k: os.environ.get(k) for k in interesting}
    logger.info("Environnement : %s", found)
    logger.info("Python %s", sys.version)

    for mod in ("mlflow", "docker"):
        try:
            m = __import__(mod)
            logger.info("%s %s importé", mod, getattr(m, "__version__", "?"))
        except ImportError as exc:
            raise RuntimeError(f"Dépendance manquante dans l'image Airflow : {exc}")
    return found


def _check_db(**_) -> str:
    """Couche 3 : Airflow atteint-il Postgres par le nom de service `db` ?

    On vise la base MÉTIER, pas la base airflow : c'est ce chemin-là que les
    futures tâches emprunteront.
    """
    import psycopg2

    dsn = (
        "host=db port=5432"
        f" dbname={os.environ.get('POSTGRES_DB', 'eco2mix')}"
        f" user={os.environ.get('POSTGRES_USER', 'eco2mix')}"
        f" password={os.environ.get('POSTGRES_PASSWORD', '')}"
    )
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, version()")
        db, user, ver = cur.fetchone()
        cur.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
            " WHERE table_schema IN ('raw','staging') ORDER BY 1,2"
        )
        tables = cur.fetchall()

    logger.info("Connecté à %s en tant que %s — %s", db, user, ver.split(",")[0])
    logger.info("Tables visibles : %s", tables or "aucune")
    return f"{db}@{user}"


with DAG(
    dag_id="my_dag_test",
    description="Recette de l'environnement Airflow — à lancer manuellement",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    schedule=None,
    catchup=False,
    tags=["recette", "infra"],
) as dag:

    # Couche 1 — le worker exécute quelque chose.
    check_bash = BashOperator(
        task_id="check_bash",
        bash_command='echo "Airflow tourne, il est $(date -Is)"',
    )

    # Couche 2 — l'environnement Python est complet.
    check_python = PythonOperator(task_id="check_python", python_callable=_check_env)

    # Couche 3 — le réseau Compose relie Airflow à Postgres.
    check_db = PythonOperator(task_id="check_db", python_callable=_check_db)

    # Couche 4 — le socket Docker répond. C'est LE prérequis du DockerOperator,
    # et la source numéro un de plantage.
    check_docker = DockerOperator(
        task_id="check_docker",
        image="alpine:3.20",
        command='sh -c "echo DockerOperator operationnel; hostname"',
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
        auto_remove="success",
        mount_tmp_dir=False,
    )

    check_bash >> check_python >> check_db >> check_docker
