"""Base de données — partie coéquipier (cadre à compléter)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402,F401  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("bdd")
theme.header("Base de données", m["minutes"], m["owner"])

theme.story(
    "Répondre à tout moment à deux questions : **d'où vient chaque donnée** (et quelles transformations elle a subies)"
    "et **sur quel jeu exact un modèle a été entraîné** — avec une seule source de vérité partagée par tous les services.",
    "Les données ODRÉ sont chargées en masse (`COPY`, via `src.data.load`) dans `staging`, puis typés et nettoyées dans `raw` (`src.data.build_raw`)"
    "Le schéma est versionné par **Alembic**. `make snapshot` fige un jeu de donnée **parquet immuable** qui sert de référence à l'entraînement."
    "MLflow et Airflow ont chacun **leur base et leur rôle** (`make db-meta`).",
)

#theme.stub("responsable de la base / ingestion", ['PostgreSQL 16 conteneurisé (`db`), volume `pgdata`, healthcheck `pg_isready`', 'Schémas `staging` → `raw` → `clean` ; migrations **Alembic**', 'Chargement : `src.data.load` (COPY) puis `src.data.build_raw` (typage)', 'Bases séparées `mlflow` et `airflow` avec **un rôle dédié par service** (`make db-meta`)', 'Snapshots parquet immuables (`make snapshot`) pour figer un jeu de données', "Table des utilisateurs de l'API (`create_users.py`)"])

#st.divider()

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=True):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **PostgreSQL 16** conteneurisé | robuste, SQL standard, déjà requis par MLflow et Airflow : une seule techno à maintenir |
| Schémas `staging` → `raw` → `clean` | chaque transformation est traçable ; on rejoue une couche sans recharger ODRÉ |
| `COPY` plutôt qu'`INSERT` | chargement en masse, adapté au volume des 4 jeux éCO2mix |
| Migrations **Alembic** | le schéma évolue avec le code, rejouable sur n'importe quel poste |
| **Snapshots parquet** immuables | un entraînement pointe un jeu figé : résultats reproductibles même si la base évolue |
| Bases et **rôles dédiés** `mlflow` / `airflow` | moindre privilège : un service compromis n'accède pas aux données métier |
| Healthcheck `pg_isready` | l'API, MLflow et Airflow ne démarrent qu'une fois la base prête |
| Volume `pgdata` | données persistantes entre les redémarrages des conteneurs |
| Table utilisateurs (`create_users.py`) | authentification de l'API sans dépendance externe |
"""
    )

st.caption(
    "Service `db` · schémas `staging` / `raw` / `clean` · bases annexes `mlflow`, `airflow` · "
    "Démarrer : `docker compose up -d db`, puis `python -m src.data.load` → "
    "`python -m src.data.build_raw` → `make snapshot`."
)
#theme.speaker_notes("bdd")
