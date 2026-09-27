"""Démo live — le champion en action : réel vs prédit, seuil k, anomalies."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("demo")
theme.header("Démo live", m["minutes"], m["owner"])

urls = da.service_urls()
b = st.columns(5)
b[0].link_button("MLflow ↗", urls["mlflow"], width="stretch")
b[1].link_button("Airflow ↗", urls["airflow"], width="stretch")
b[2].link_button("API /docs ↗", urls["api"] + "/docs", width="stretch")
b[3].link_button("Grafana ↗", urls["grafana"], width="stretch")
b[4].link_button("Silo ↗", urls["silo"], width="stretch")

with st.expander("Déroulé conseillé (5 min)", expanded=False):
    st.markdown(
        """
1. **Ici** — fenêtre centrée sur la plus forte anomalie ; bouger *k* (≈ 1 min 30).
2. **Airflow** — le DAG `retrain_eco2mix` et son dernier run (≈ 1 min).
3. **MLflow** — le nouveau run, la version, l'alias `@champion` (≈ 1 min).
4. **API /docs** — `/token` puis `/predict` (≈ 1 min).
5. **Grafana** — les requêtes qui viennent d'arriver (≈ 30 s).
"""
    )

info, err = da.get_artifact_info()
theme.stop_on(err, "Entraîner un modèle (`make train`) ou démarrer MLflow pour charger le champion.")
scores, err = da.get_scores()
theme.stop_on(err)

st.caption(f"Modèle servi : `{info['version']}` · origine **{info['origine']}** · "
           f"{info['n_features']} features · σ robuste {info['resid_scale']:.0f} MW")

dates = scores.select("date_heure").to_series()
dmin, dmax = dates.min().date(), dates.max().date()
step_min = max(1, int(dates.head(200).diff().drop_nulls().median().total_seconds() // 60))
max_days = max(1, min(60, theme.MAX_POINTS // (1440 // step_min)))

default_end = dmax
top0, _ = da.get_top_anomalies(info["k"], 1)
if top0 is not None and top0.height:
    default_end = min(dmax, top0.row(0, named=True)["date_heure"].date() + timedelta(days=3))

c1, c2, c3 = st.columns([2, 2, 3])
end = c1.date_input("Fin de la fenêtre", value=default_end, min_value=dmin, max_value=dmax,
                    help="Par défaut : 3 jours après l'anomalie la plus forte de l'historique.")
days = c2.slider("Nombre de jours", 1, max_days, min(10, max_days))
k = c3.slider("Seuil k", 1.0, 10.0, float(round(info["k"], 1)), 0.1,
              help="Recalcule is_anomaly = anomaly_score > k en direct.")

win, err = da.get_score_window(end, days, k)
theme.stop_on(err)
if win.height == 0:
    theme.stop_on("Aucun point dans cette fenêtre.", level="info")

pdf = win.select("date_heure", "y_true", "y_pred", "residual", "anomaly_score", "is_anomaly").to_pandas()
n_anom = int(pdf["is_anomaly"].sum())

long = pdf.melt(id_vars=["date_heure"], value_vars=["y_true", "y_pred"], var_name="serie", value_name="mw")
long["serie"] = long["serie"].map({"y_true": "Réel", "y_pred": "Prédit (ŷ)"})
dom = ["Réel", "Prédit (ŷ)"]
x = alt.X("date_heure:T", title=None)
lines = (alt.Chart(long).mark_line(strokeWidth=1.8)
         .encode(x=x, y=alt.Y("mw:Q", title="MW", scale=alt.Scale(zero=False)),
                 color=alt.Color("serie:N", title=None, scale=alt.Scale(domain=dom, range=[theme.REEL, theme.PREDIT]),
                                 legend=alt.Legend(orient="top")),
                 strokeDash=alt.StrokeDash("serie:N", legend=None,
                                           scale=alt.Scale(domain=dom, range=[[1, 0], [5, 3]])),
                 tooltip=[alt.Tooltip("date_heure:T", format="%d/%m %H:%M"), "serie:N",
                          alt.Tooltip("mw:Q", format=",.0f")]))
points = (alt.Chart(pdf[pdf["is_anomaly"]])
          .mark_point(filled=True, size=70, color=theme.ANOMALIE, stroke="white", strokeWidth=0.8)
          .encode(x=x, y="y_true:Q",
                  tooltip=[alt.Tooltip("date_heure:T", title="Anomalie", format="%d/%m/%Y %H:%M"),
                           alt.Tooltip("y_true:Q", title="Réel", format=",.0f"),
                           alt.Tooltip("y_pred:Q", title="ŷ", format=",.0f"),
                           alt.Tooltip("anomaly_score:Q", title="score", format=".2f")]))
st.altair_chart((lines + points).properties(height=320).interactive(bind_y=False), width="stretch")

score_chart = (alt.Chart(pdf)
               .mark_area(line={"color": theme.REEL, "strokeWidth": 1.2}, color=theme.REEL, opacity=0.15)
               .encode(x=x, y=alt.Y("anomaly_score:Q", title="score s_t")))
rule = (alt.Chart({"values": [{"k": k}]})
        .mark_rule(color=theme.NEUTRE, strokeDash=[6, 4], strokeWidth=1.5).encode(y="k:Q"))
above = (alt.Chart(pdf[pdf["is_anomaly"]]).mark_point(filled=True, size=45, color=theme.ANOMALIE)
         .encode(x=x, y="anomaly_score:Q"))
st.altair_chart((score_chart + rule + above).properties(height=170), width="stretch")
st.caption(f"{len(pdf)} points · **{n_anom} anomalie(s)** à k = {k:.1f} (vermillon) · "
           f"ligne pointillée = seuil k")

left, right = st.columns([3, 2])
with left:
    st.markdown("**Anomalies de la fenêtre**")
    if n_anom:
        tab = (pdf[pdf["is_anomaly"]].sort_values("anomaly_score", ascending=False)
               .drop(columns=["is_anomaly"]).head(12))
        st.dataframe(tab, width="stretch", hide_index=True,
                     column_config={"date_heure": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                                    "y_true": st.column_config.NumberColumn(format="%.0f"),
                                    "y_pred": st.column_config.NumberColumn(format="%.0f"),
                                    "residual": st.column_config.NumberColumn(format="%.0f"),
                                    "anomaly_score": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.info("Aucune anomalie dans la fenêtre à ce seuil.")
with right:
    st.markdown("**Nombre d'anomalies sur tout l'historique selon k**")
    grid = [round(1.0 + 0.25 * i, 2) for i in range(37)]
    counts, cerr = da.get_anomaly_counts(grid)
    if cerr:
        st.info(cerr)
    else:
        curve = (alt.Chart(counts.to_pandas()).mark_line(color=theme.REEL, point=True)
                 .encode(x=alt.X("k:Q"), y=alt.Y("n_anomalies:Q", title="anomalies", scale=alt.Scale(type="symlog")),
                         tooltip=["k:Q", alt.Tooltip("n_anomalies:Q", format=",")]))
        now = (alt.Chart({"values": [{"k": k}]}).mark_rule(color=theme.ANOMALIE, strokeDash=[4, 3])
               .encode(x="k:Q"))
        st.altair_chart((curve + now).properties(height=220), width="stretch")

with st.expander("Top anomalies de l'historique"):
    top, terr = da.get_top_anomalies(k, 15)
    if terr:
        st.info(terr)
    elif top.height:
        st.dataframe(top.to_pandas(), width="stretch", hide_index=True)
theme.speaker_notes("demo")
