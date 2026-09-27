"""Streamlit — l'app de démo comme composant de l'architecture."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("streamlit")
theme.header("Streamlit — la vitrine", m["minutes"], m["owner"])

theme.story(
    "Montrer le système **vivant** à un public non technique comme à un jury, "
    "à partir des vraies sources — pas de captures d'écran figées.",
    "Une app Streamlit locale (0.0.0.0:8501) qui lit **les mêmes briques que la prod** : "
    "la base via `load_features()`, le champion via `resolve_artifact()`, le registre via "
    "l'API MLflow.",
)

DOT = f"""
digraph app {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.3; ranksep=0.5;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10.5,
        fillcolor="{theme.TEAM_FILL}", color="#56606b"];
  edge [color="#56606b", fontname="Helvetica", fontsize=9, arrowsize=0.7];
  views [label="views/*.py\\n(une page = une section du plan)", fillcolor="{theme.MINE_FILL}", color="{theme.REEL}"];
  da    [label="lib/data_access.py\\nseul point d'accès\\nrenvoie (donnée, erreur)", fillcolor="{theme.MINE_FILL}", color="{theme.REEL}", penwidth=2];
  src   [label="src.* (import paresseux)\\nload_features · resolve_artifact · score"];
  ml    [label="MLflow\\nsearch_runs · registry"];
  db    [label="PostgreSQL", shape=cylinder];
  views -> da -> src -> db;
  da -> ml;
}}
"""
st.graphviz_chart(DOT, width="stretch")

st.markdown(
    """
| Choix | Pourquoi |
|---|---|
| Un **seul module d'accès** (`lib/data_access.py`) | les pages ne connaissent pas `src.*` ; on pourra basculer vers l'API (`ANOM_APP_SOURCE=api`) sans toucher aux pages |
| Retour **`(donnée, erreur)`** | un service éteint affiche un message, la page ne plante pas — vérifié par des tests headless (`AppTest`) |
| **Cache** Streamlit | modèle et client MLflow en `cache_resource`, données en `cache_data` : la démo reste fluide |
| **polars** puis `.to_pandas()` sur < 5 000 points | agrégation côté moteur rapide, graphiques Altair légers |
| Palette **Okabe-Ito** | lisible par les daltoniens ; une couleur = un sens (vermillon réservé aux anomalies) |
"""
)

status = da.get_services_status()
up = sum(s["ok"] for s in status) + 0
st.caption(f"Services joignables à l'instant : {up}/{len(status)} — l'app s'adapte à ce qui tourne.")

theme.conclusion(
    "l'app est un **client comme un autre** de l'architecture : elle réutilise le code de "
    "prod au lieu de le dupliquer, et elle dégrade proprement si une brique manque."
)
theme.speaker_notes("streamlit")
