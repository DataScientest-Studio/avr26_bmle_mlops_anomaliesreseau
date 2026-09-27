"""Contexte & modèle maison — le problème, puis le modèle construit from scratch."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("contexte")
theme.header("Contexte & modèle maison")#, m["minutes"], m["owner"])

theme.story(
    "Repérer automatiquement les demi-heures où la **consommation électrique nationale** "
    "s'écarte de ce que le calendrier et la saison laissent attendre — et livrer ce "
    "détecteur comme un **service MLOps complet**, pas comme un notebook.",
    "Un modèle **construit par nous** : une régression tabulaire prédit la conso « normale » "
    "à partir de features temporelles ; l'anomalie est le **résidu robuste** au-delà d'un "
    "seuil *k*. Pas de modèle pré-entraîné, pas de modèle de série temporelle.",
)

# -----------------------------------------------------------------------------
st.subheader("Les données")
summary, err = da.get_features_summary()
c1, c2, c3, c4 = st.columns(4)
c1.markdown("**Source**  \néCO2mix national (RTE / ODRE)")
if err is None:
    c2.metric("Pas de temps", "30 min")
    c3.metric("Période", f"{str(summary['date_min'])[:4]} → {str(summary['date_max'])[:4]}")
    c4.metric("Lignes", f"{summary['n_rows']:,}".replace(",", " "))
else:
    c2.metric("Pas de temps", "30 min")
    c3.caption("Données non chargées — démarrer la base pour les chiffres.")
st.caption("Arrivée des données simulée année par année (curseur `max_year.conf`) : "
           "chaque exécution du DAG Airflow ajoute une année et réentraîne.")

# -----------------------------------------------------------------------------
st.subheader("Pourquoi un modèle « maison » sur des features calendaires ?")
left, right = st.columns([3, 2])
with left:
    prof, perr = da.get_calendar_profile()
    if perr:
        st.info(f"Graphique indisponible : {perr}")
    else:
        pdf = prof.to_pandas()
        chart = (
            alt.Chart(pdf)
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X("hour:Q", title="Heure", scale=alt.Scale(domain=[0, 23])),
                y=alt.Y("conso_moy:Q", title="Conso moyenne (MW)", scale=alt.Scale(zero=False)),
                color=alt.Color("type_jour:N", title=None,
                                scale=alt.Scale(domain=["Jour ouvré", "Week-end / férié"],
                                                range=[theme.OUVRE, theme.CHOME]),
                                legend=alt.Legend(orient="top")),
                tooltip=["type_jour:N", "hour:Q", alt.Tooltip("conso_moy:Q", format=",.0f")],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, width="stretch")
        st.caption("Même heure, pas le même jour : le calendrier explique l'essentiel de la courbe.")
with right:
    st.markdown(
        """
- **Calendrier FR** : fériés, ponts, vacances zone C, heure d'été, week-end.
- **Fourier** jour / semaine / année : saisonnalités lisses.
- **Lags** 1 j / 7 j et moyennes glissantes : niveau récent.
- **Exclus exprès** : la prévision RTE (elle « donne la réponse ») et la
  production par filière (contemporaine).
"""
    )

# -----------------------------------------------------------------------------
st.subheader("Le modèle et la règle d'anomalie")
f1, f2 = st.columns([3, 2])
with f1:
    st.latex(r"\hat{y}_t = f(\text{calendrier}_t,\ \text{Fourier}_t,\ \text{lags}_t)")
    st.latex(r"s_t = \frac{\lvert (y_t - \hat{y}_t) - \operatorname{med}(r) \rvert}"
             r"{1.4826 \cdot \operatorname{MAD}(r)} \quad\Rightarrow\quad \text{anomalie si } s_t > k")
    st.caption("Médiane et MAD calculées sur les résidus de **validation** (80/20 chronologique, "
               "sans mélange) : le seuil n'est pas tiré par les anomalies elles-mêmes.")
with f2:
    with st.container(border=True):
        st.markdown("**Choix retenus**")
        st.markdown(
            "- `HistGradientBoosting` (option `linear`)\n"
            "- pas de time-series : 1 ligne = 1 prédiction → API sans état\n"
            "- seuil par défaut *k* = 3,5\n"
            "- baselines de référence : persistance J-7 (B1), écart prévision RTE (B2)"
        )
        if err is None:
            n_feat = len(summary["calendar"]) + len(summary["fourier"]) + len(summary["lags"])
            st.metric("Features temporelles", n_feat)

theme.conclusion(
    "un modèle volontairement simple, explicable et rapide à réentraîner : l'enjeu du "
    "projet n'est pas la performance du modèle mais **tout ce qui l'entoure** — données, "
    "suivi, versioning, service, orchestration, monitoring."
)
theme.speaker_notes("contexte")
