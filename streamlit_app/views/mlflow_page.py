"""MLflow (Ludo) — suivi d'expériences, Model Registry, champion."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("mlflow")
theme.header("MLflow — suivi & registre des modèles", m["minutes"], m["owner"])
names = da.get_names()

theme.story(
    "Répondre à tout moment à deux questions : **qu'a-t-on essayé** (et avec quel résultat) "
    "et **quel modèle est servi en production** — sans ambiguïté ni copie de fichier.",
    "Chaque entraînement logue un **run** (params, `mae_valid`, seuil en JSON) et crée une "
    "**version** au registre. L'alias **@champion** n'est déplacé que si la MAE de validation "
    "bat celle du champion ; l'API charge toujours `models:/…@champion`.",
)

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=False):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **MLflow** auto-hébergé | open source, tracking + registre dans un seul outil, format de modèle standard (sklearn / pyfunc) |
| **Alias `@champion`** plutôt que les *stages* | les stages sont dépréciés ; un alias se déplace en une opération, le rollback aussi |
| Backend **PostgreSQL** (base et rôle `mlflow` dédiés) | durable, déjà dans la stack, cloisonné des données métier |
| Artefacts sur **Silo (S3)** via `--serve-artifacts` | seuls les conteneurs MLflow connaissent les clés S3 ; l'API et Airflow passent par HTTP |
| Silo (fork MinIO) | image MinIO retirée de Docker Hub le 11/09/2026, plus de correctifs |
| Promotion **dans le code** (`_promote_if_better`) | une seule source de vérité : Airflow orchestre, le code décide |
| Repli `models/model.joblib` | l'entraînement et le scoring fonctionnent même MLflow éteint |
"""
    )

top_l, top_r = st.columns([4, 1])
top_l.caption(f"Serveur `{names['uri']}` · expérience `{names['experiment']}` · modèle `{names['model_name']}`")
top_r.link_button("Ouvrir l'UI MLflow ↗", names["ui"], width="stretch")

reg, err = da.get_registry()
theme.stop_on(err, "Démarrer MLflow (`make mlflow` ou `docker compose up -d mlflow`), exporter "
                   "`MLFLOW_TRACKING_URI=http://localhost:5000`, puis `make train`.")
versions, champ = reg
runs, runs_err = da.get_mlflow_runs()

# --- Bandeau champion ---------------------------------------------------------
if champ is None:
    st.warning(f"Aucune version ne porte l'alias @{names['alias']}.")
else:
    crun = None
    if runs_err is None:
        match = runs.filter(pl.col("run_id") == champ["run_id"])
        crun = match.row(0, named=True) if match.height else None
    with st.container(border=True):
        st.markdown(f"#### 🏆 Champion servi : `{names['model_name']}` version **{champ['version']}**")
        b1, b2, b3, b4 = st.columns(4)
        mae = (crun or {}).get("mae_valid")
        b1.metric("MAE validation", f"{mae:,.0f} MW".replace(",", " ") if mae is not None else "—")
        b2.metric("Versions au registre", versions.height)
        b3.metric("Runs loggés", runs.height if runs_err is None else "—")
        b4.metric("Promu le", champ["created"][:10])

# --- Courbe MAE + versions ------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.markdown("**MAE de validation par run et règle de promotion**")
    if runs_err:
        st.info(runs_err)
    else:
        champ_run = champ["run_id"] if champ else None
        plot = runs.filter(pl.col("mae_valid").is_not_null()).with_columns(
            (pl.col("run_id") == champ_run).fill_null(False).alias("champion"),
            pl.col("git_commit").fill_null("?"),
            pl.col("data_hash").fill_null("?").str.slice(0, 12),
        )
        if plot.height == 0:
            st.info("Aucun run avec la métrique mae_valid.")
        else:
            pdf = plot.to_pandas()
            tip = [alt.Tooltip("run_no:Q", title="run #"),
                   alt.Tooltip("mae_valid:Q", title="MAE", format=",.0f"),
                   "git_commit:N", "data_hash:N", alt.Tooltip("start_time:T", format="%d/%m %H:%M")]
            x = alt.X("run_no:Q", title="run (ordre chronologique)", axis=alt.Axis(tickMinStep=1))
            y = alt.Y("mae_valid:Q", title="MAE validation (MW)", scale=alt.Scale(zero=False))
            line = alt.Chart(pdf).mark_line(color=theme.REEL, strokeWidth=2).encode(x=x, y=y)
            pts = alt.Chart(pdf).mark_point(filled=True, size=60, color=theme.REEL).encode(x=x, y=y, tooltip=tip)
            best = (alt.Chart(pdf).transform_window(best="min(mae_valid)", frame=[None, 0])
                    .mark_line(color=theme.NEUTRE, strokeDash=[4, 3], interpolate="step-after")
                    .encode(x=x, y="best:Q"))
            ch = (alt.Chart(pdf[pdf["champion"]])
                  .mark_point(shape="diamond", filled=True, size=220, color=theme.CHAMPION,
                              stroke="black", strokeWidth=0.6).encode(x=x, y=y, tooltip=tip))
            st.altair_chart((line + best + pts + ch).properties(height=280), width="stretch")
            st.caption("Pointillés : meilleure MAE atteinte jusque-là = seuil à battre pour devenir champion. "
                       "Losange pourpre : champion actuel.")

with right:
    st.markdown("**Versions du registre**")
    vdf = versions.to_pandas()
    vdf.insert(0, "champion", vdf.pop("is_champion").map({True: "🏆", False: ""}))
    st.dataframe(vdf[["champion", "version", "created", "status", "run_id"]], width="stretch",
                 hide_index=True, height=280)

theme.conclusion(
    "le modèle servi n'est jamais « le dernier fichier écrit » mais **la meilleure version "
    "validée**, désignée par un alias ; promouvoir ou revenir en arrière = déplacer l'alias, "
    "puis `/reload` sur l'API."
)
theme.speaker_notes("mlflow")
