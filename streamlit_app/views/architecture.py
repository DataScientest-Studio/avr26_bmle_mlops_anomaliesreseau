"""Architecture — schéma d'ensemble + état des services."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("architecture")
theme.header("Architecture")#, m["minutes"], m["owner"])

theme.story(
    "Faire tourner tout le cycle de vie du modèle — données, entraînement, registre, "
    "service, orchestration, monitoring — **en local et en open source**, sans cloud propriétaire.",
    "Une stack **docker-compose** sur un réseau interne `mlops-net` ; chaque brique est un "
    "service remplaçable. Airflow orchestre, MLflow arbitre quel modèle est servi, "
    "l'API le sert, Prometheus/Grafana le surveillent.",
)

MINE, TEAM = theme.MINE_FILL, theme.TEAM_FILL
BLUE = theme.REEL
DOT = f"""
digraph archi {{
  rankdir=LR; bgcolor="transparent"; splines=spline; nodesep=0.35; ranksep=0.55;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=15,
        color="#56606b", fillcolor="{TEAM}", penwidth=1.2, margin="0.15,0.08"];
  edge [color="#56606b", fontname="Helvetica", fontsize=12, arrowsize=0.8];

  csv    [label="éCO2mix\\n(RTE / ODRE)", shape=cylinder, fillcolor="white"];
  af     [label="airflow\\nDAG retrain_eco2mix\\ningest → build_raw\\n→ train → reload_api"];
  db     [label="db · PostgreSQL\\nun rôle par service", shape=cylinder];
  train  [label="train\\nfeatures polars\\nHGB + résidu robuste", fillcolor="{MINE}", color="{BLUE}", penwidth=2];
  mlflow [label="mlflow\\ntracking + registry\\n@champion", fillcolor="{MINE}", color="{BLUE}", penwidth=2];
  vers   [label="versioning\\ngit_commit · data_hash", fillcolor="{MINE}", color="{BLUE}", penwidth=2];
  silo   [label="silo · S3\\nartefacts", shape=cylinder];
  api    [label="api · FastAPI\\n/predict /reload"];
  prom   [label="prometheus"];
  graf   [label="grafana"];
  st     [label="streamlit", shape=note, fillcolor="{MINE}", color="{BLUE}", penwidth=2];

  csv -> af [label="1 · ingestion"];
  af -> db;
  db -> train [label="2 · features"];
  af -> train [style=dashed, label="DockerOperator"];
  train -> mlflow [label="3 · run + version"];
  vers -> mlflow [style=dashed, arrowhead=none];
  mlflow -> silo [style=dashed];
  mlflow -> api [label="4 · @champion"];
  api -> prom [label="5 · /metrics"];
  prom -> graf;
  st -> mlflow [style=dotted];
  {{ rank=same; mlflow; vers; }}
  {{ rank=same; api; silo; }}
}}
"""
st.graphviz_chart(DOT, width="stretch")
st.caption("Bleu : parties de Ludo (modèle, MLflow, versioning, Streamlit). Gris : parties des coéquipiers. "
           "Tous les services sont des conteneurs sur le réseau `mlops-net`, exposés sur 0.0.0.0 "
           "sauf la console Silo (127.0.0.1) ; l'API S3 de Silo reste interne.")

# -----------------------------------------------------------------------------
st.subheader("Le cycle en une phrase par étape")
st.markdown(
    """
| Étape | Qui | Ce qui se passe |
|---|---|---|
| 1. Ingestion | Airflow → `ingest`, `build_raw` | une année de plus arrive, chargée dans PostgreSQL |
| 2. Entraînement | Airflow → `train` | features polars, modèle, seuil robuste, **run MLflow** |
| 3. Décision | MLflow | nouvelle version ; alias **@champion** déplacé si la MAE baisse |
| 4. Service | Airflow → `reload_api` → API | l'API recharge le champion, sert `/predict` |
| 5. Surveillance | Prometheus → Grafana | latence, volume, erreurs de l'API |
"""
)

# -----------------------------------------------------------------------------
head, btn = st.columns([4, 1])
head.subheader("État des services")
if btn.button("↻ Rafraîchir", width="stretch"):
    da.clear_caches()
    st.rerun()

status = da.get_services_status()
cols = st.columns(len(status))
for col, s in zip(cols, status):
    with col.container(border=True):
        state = ":blue[● en ligne]" if s["ok"] else ":orange[○ hors ligne]"
        st.markdown(f"**{s['service']}**  \n{state}")
with st.expander("Rôle de chaque service et détail des sondes"):
    for s in status:
        st.markdown(f"- **{s['service']}** — {s['role']} · `{s['detail']}`")

theme.conclusion(
    "une architecture **modulaire** : on peut remplacer le modèle, le stockage ou "
    "l'orchestrateur sans toucher au reste, parce que les contrats entre briques sont "
    "simples (une table, un alias MLflow, une route HTTP)."
)
theme.speaker_notes("architecture")
