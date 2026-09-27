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
theme.stub("responsable de la base / ingestion", ['PostgreSQL 16 conteneurisé (`db`), volume `pgdata`, healthcheck `pg_isready`', 'Schémas `staging` → `raw` → `clean` ; migrations **Alembic**', 'Chargement : `src.data.load` (COPY) puis `src.data.build_raw` (typage)', 'Bases séparées `mlflow` et `airflow` avec **un rôle dédié par service** (`make db-meta`)', 'Snapshots parquet immuables (`make snapshot`) pour figer un jeu de données', "Table des utilisateurs de l'API (`create_users.py`)"])
theme.speaker_notes("bdd")
