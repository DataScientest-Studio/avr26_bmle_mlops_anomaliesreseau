"""Prometheus & Grafana — voir la production en direct plutôt que la supposer saine."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("grafana")
theme.header("Prometheus & Grafana", m["minutes"], m["owner"])

theme.story(
    "Savoir **avant l'incident** que le modèle servi dérive, que l'API ralentit ou se "
    "met à renvoyer des erreurs.",
    "L'API expose déjà ses métriques sur `/metrics`. Prometheus les collecte toutes les "
    "5 secondes, et Grafana les rend lisibles. Deux dashboards, préchargés au démarrage, "
    "couvrent l'API et la dérive du modèle.",
)

# -----------------------------------------------------------------------------
st.subheader("La chaîne de collecte")
st.markdown(
    """
`prometheus-fastapi-instrumentator` instrumente l'API → l'API expose le résultat sur
`/metrics` → Prometheus la scrape **toutes les 5 s** → Grafana lit ses données chez
Prometheus → deux dashboards JSON sont chargés au démarrage dans le dossier Grafana
`MLOps`.
"""
)
st.code(
    """# monitoring/prometheus/prometheus.yaml
global:
  scrape_interval: 5s
scrape_configs:
  - job_name: "fastapi-anomaly-api"
    metrics_path: "/metrics"
    static_configs:
      - targets: ["api:8000"]""",
    language="yaml",
)
st.caption("Grafana n'interroge jamais l'API : il ne lit que la base de séries temporelles de "
           "Prometheus. C'est ce qui permet de rejouer l'historique après un incident.")

# -----------------------------------------------------------------------------
st.subheader("Deux familles de métriques")
s1, s2 = st.columns(2)
with s1:
    st.markdown("**Métriques techniques** (fournies par l'instrumentateur)")
    st.markdown(
        """
| Métrique | Question à laquelle elle répond |
|---|---|
| `http_requests_total` | combien de requêtes, sur quelles routes, avec quels codes ? |
| `http_request_duration_seconds_*` | quelle latence, et jusqu'où elle monte (p99) ? |
| `http_request_size_bytes` / `http_response_size_bytes` | quel volume de données échangé ? |
| `process_resident_memory_bytes` | la mémoire du processus tient-elle ? |
| `process_cpu_seconds_total` | le CPU est-il saturé, ou en fuite ? |
"""
    )
with s2:
    st.markdown("**Métriques métier** (les `Gauge` du projet)")
    st.markdown(
        """
| Métrique | Signification |
|---|---|
| `model_feature_drift_ks_pvalue{feature}` | p-value du test KS, par feature — dérive si < 0,05 |
| `model_drifted_features_ratio` | **part des features en dérive**, en % |
| `model_prediction_mean` | moyenne des prédictions servies |

Elles sont déclarées dans `src/models/main_api.py`. C'est le seul endroit de la chaîne
qui connaît le métier : les métriques techniques, elles, restent génériques.
"""
    )

# -----------------------------------------------------------------------------
st.subheader("État live")
up, err = da.get_prom_query("up")
if err:
    st.info(err)
    st.caption("Les métriques ci-dessous se remplissent dès que Prometheus scrape l'API "
               "(`docker compose up -d prometheus grafana api`).")
else:
    ratio, _ = da.get_prom_scalar("model_drifted_features_ratio")
    pred, _ = da.get_prom_scalar("model_prediction_mean")
    n_ks, _ = da.get_prom_scalar("count(model_feature_drift_ks_pvalue)")
    ratio_s = f"{ratio:.1f} %" if ratio is not None else "—"
    pred_s = f"{pred:,.0f} MW".replace(",", " ") if pred else "—"
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("API scrapée", "🟢 active" if up and up[0]["value"] == 1 else "🔴 injoignable")
    b2.metric("Features en dérive", ratio_s, help="Part des features dont la p-value KS est < 0,05.")
    b3.metric("Prédiction moyenne", pred_s)
    n_ks_val = int(n_ks) if n_ks is not None else 0
    b4.metric("Features testées", n_ks_val, help="Le test KS démarre une fois 5 appels à /predict.")

    if n_ks_val == 0:
        st.caption(
            "Le test de dérive démarre après **5 requêtes `/predict`** (la taille du "
            "buffer de l'API) : `model_feature_drift_ks_pvalue` n'a donc encore aucune "
            "série. Cinq appels à `/predict` depuis Swagger suffisent à faire apparaître "
            "la première."
        )
    else:
        ks, ks_err = da.get_prom_query("model_feature_drift_ks_pvalue")
        if ks_err:
            st.info(ks_err)
        elif ks:
            pdf = (pl.DataFrame({"feature": [s["labels"].get("feature", "?") for s in ks],
                                 "p": [s["value"] for s in ks]}).sort("p"))
            drift = pdf.filter(pl.col("p") < 0.05)
            c1, c2 = st.columns([3, 2])
            with c1:
                chart = (alt.Chart(pdf.to_pandas()).mark_bar(color=theme.REEL)
                         .encode(x=alt.X("feature:N", title=None,
                                         sort=alt.EncodingSortField("p", order="ascending")),
                                 y=alt.Y("p:Q", title="p-value du test KS", scale=alt.Scale(zero=False)),
                                 tooltip=["feature:N", alt.Tooltip("p:Q", format=".4f")]))
                rule = (alt.Chart({"values": [{"seuil": 0.05}]})
                        .mark_rule(color=theme.ANOMALIE, strokeDash=[4, 3], strokeWidth=1.5)
                        .encode(y="seuil:Q"))
                st.altair_chart((chart + rule).properties(height=260), width="stretch")
                st.caption("Les features sont triées par p-value croissante : les plus "
                           "dérivees sont à gauche. Toute barre sous le seuil de 0,05 "
                           "signale une distribution qui a bougé.")
            with c2:
                if drift.height:
                    st.error(f"**{drift.height} feature(s) en dérive** — le modèle est servi "
                             f"sur des données qui ne ressemblent plus à celles de son "
                             f"entraînement.")
                    st.dataframe(drift.head(10).to_pandas(),
                                 width="stretch", hide_index=True,
                                 column_config={"p": st.column_config.NumberColumn(format="%.4f")})
                else:
                    st.success("**Aucune dérive détectée** : toutes les p-values sont au-dessus de 0,05.")
                st.link_button("Ouvrir le dashboard de dérive ↗",
                               f"{da.service_urls()['grafana']}/d/"
                               "75e00805-13a4-4c54-b18f-1dc01194a007", width="stretch")

# -----------------------------------------------------------------------------
st.subheader("Les deux dashboards")
d1, d2 = st.columns(2)
with d1:
    st.markdown("**FastAPI Observability** — 10 panneaux")
    st.markdown(
        """
Cartographie des temps de réponse, requêtes/seconde, nombre de requêtes, part de 2xx,
part de 5xx, mémoire résidente, CPU, total cumulé, durée moyenne et **p99**.
C'est le tableau de bord « l'API tient-elle debout ? ».
"""
    )
with d2:
    st.markdown("**MLOps - Model & Drift Monitoring** — 4 panneaux")
    st.markdown(
        """
Dérive globale en %, **p-value KS par feature** avec le seuil critique à 0,05, nombre
de variables en dérive, et consommation moyenne prédite. C'est le tableau de bord
« le modèle a-t-il encore du sens ? ».
"""
    )
st.caption("Les deux sont décrits en JSON, dans le dépôt, et Grafana les relit toutes "
           "les 10 s. Modifier un dashboard revient donc à modifier du code versionné.")

theme.conclusion(
    "la supervision ne sert pas à confirmer que « tout va bien », mais à **mesurer la "
    "dérive entre les données d'entraînement et celles qui arrivent en production** — "
    "un signal qui déclenche un ré-entraînement, et le premier suspect quand les "
    "prédictions se dégradent."
)

c1, c2 = st.columns(2)
c1.link_button("Ouvrir Grafana ↗", da.service_urls()["grafana"], width="stretch")
c2.link_button("Ouvrir Prometheus ↗", da.service_urls()["prometheus"], width="stretch")
theme.speaker_notes("grafana")
