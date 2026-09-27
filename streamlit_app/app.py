"""Soutenance MLOps — détection d'anomalies sur la consommation électrique.

Lancement (depuis la racine du repo) :
    uv run streamlit run streamlit_app/app.py --server.address 0.0.0.0 --server.port 8501
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # rend `lib` importable depuis les vues

from lib import plan  # noqa: E402

st.set_page_config(page_title="Anomalies conso — soutenance MLOps", layout="wide")

sections: dict[str, list] = {}
for key, file, title, icon, minutes, owner, section in plan.PLAN:
    sections.setdefault(section, []).append(
        st.Page(str(HERE / file), title=title, url_path=key, default=(key == "contexte"))
    )

st.navigation(sections).run()