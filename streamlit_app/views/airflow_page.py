"""Airflow — partie coéquipier (cadre à compléter)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402,F401  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("airflow")
theme.header("Airflow", m["minutes"], m["owner"])
theme.stub("responsable de l'orchestration", ['DAG `retrain_eco2mix`, quotidien 4 h : `ingest → build_raw → train → reload_api`', "**DockerOperator** : chaque tâche tourne dans l'image applicative (pas de dépendances ML dans Airflow)", "Pas de tâche de promotion : c'est MLflow (`_promote_if_better`) qui décide → une seule source de vérité", 'Curseur `max_year.conf` : une année de plus à chaque exécution (arrivée de données simulée)', "Fichier compose séparé + profil `airflow` (n'impacte pas `make up`)", '`max_active_runs=1`, 2 retries, timeouts par tâche'])
st.link_button("Ouvrir Airflow ↗", da.service_urls()["airflow"])
theme.speaker_notes("airflow")
