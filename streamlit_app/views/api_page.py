"""API FastAPI — partie coéquipier (cadre à compléter)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402,F401  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("api")
theme.header("API FastAPI", m["minutes"], m["owner"])
theme.stub("responsable de l'API", ['Routes : `/token` (JWT), `/verify`, `/predict`, `/train` et `/reload` (admin), `/metrics`', 'Au démarrage : charge `models:/anomalies_conso_national@champion` depuis MLflow', '`/reload` appelé par Airflow après chaque entraînement → pas de redémarrage', "Schéma d'entrée validé par Pydantic (`FeatureRow`)", 'Conteneur non-root (`appuser`), healthcheck sur `/verify`', 'Instrumentation Prometheus (`prometheus-fastapi-instrumentator`)'])
st.link_button("Ouvrir la doc Swagger ↗", da.service_urls()["api"] + "/docs")
theme.speaker_notes("api")
