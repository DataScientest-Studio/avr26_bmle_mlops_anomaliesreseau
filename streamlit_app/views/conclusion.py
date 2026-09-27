"""Conclusion."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import plan, theme  # noqa: E402

m = plan.meta("conclusion")
theme.header("Conclusion", m["minutes"], m["owner"])

c1, c2, c3 = st.columns(3)
with c1.container(border=True, height="stretch"):
    st.markdown("#### Un modèle simple…")
    st.markdown("régression sur features calendaires + résidu robuste : explicable, "
                "rapide à réentraîner, facile à servir.")
with c2.container(border=True, height="stretch"):
    st.markdown("#### …dans un cycle complet")
    st.markdown("ingestion → entraînement → registre → service → monitoring, "
                "orchestré par Airflow, 100 % open source et local.")
with c3.container(border=True, height="stretch"):
    st.markdown("#### …traçable de bout en bout")
    st.markdown("chaque modèle servi se relie à un commit, une empreinte de données "
                "et une MAE ; promotion et rollback = un alias.")

st.divider()
st.markdown("### Merci — place aux questions")
theme.speaker_notes("conclusion")
