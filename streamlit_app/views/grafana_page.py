"""Prometheus & Grafana — partie coéquipier (cadre à compléter)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402,F401  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("grafana")
theme.header("Prometheus & Grafana", m["minutes"], m["owner"])
theme.stub("responsable du monitoring", ['Prometheus scrape `api:8000/metrics` toutes les 5 s (`prometheus.yaml`)', "Métriques HTTP : latence, débit, codes d'erreur par route", 'Grafana sur :3000, source de données Prometheus', "Idées : taux d'anomalies prédites, version du modèle servie, alertes"])
c1, c2 = st.columns(2)
c1.link_button("Ouvrir Grafana ↗", da.service_urls()["grafana"], width="stretch")
c2.link_button("Ouvrir Prometheus ↗", da.service_urls()["prometheus"], width="stretch")
theme.speaker_notes("grafana")
