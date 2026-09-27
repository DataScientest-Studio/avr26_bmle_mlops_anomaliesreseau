"""Versioning (Ludo) — code, données, environnement, modèle : la chaîne de traçabilité."""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402
from lib import plan, theme  # noqa: E402

m = plan.meta("versioning")
theme.header("Versioning — code, données, modèle", m["minutes"], m["owner"])

theme.story(
    "Pouvoir dire, pour **n'importe quel modèle servi** : avec quel code, sur quelles "
    "données et dans quel environnement il a été produit — et le reproduire.",
    "Quatre choses versionnées, chacune avec l'outil le plus léger possible, toutes "
    "rattachées au **run MLflow** qui fait le lien.",
)

LINEAGE = f"""
digraph lineage {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.3; ranksep=0.5;
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10.5,
        fillcolor="{theme.MINE_FILL}", color="{theme.REEL}", penwidth=1.6];
  edge [color="#56606b", fontname="Helvetica", fontsize=9, arrowsize=0.7];
  code [label="Code\\ngit commit"];
  env  [label="Environnement\\nuv.lock · image Docker"];
  data [label="Données\\ndata_hash (SHA-256 de X, y)\\nn_rows · date_min/max"];
  run  [label="Run MLflow\\nparams + mae_valid", fillcolor="white"];
  ver  [label="Version N\\nau registre", fillcolor="white"];
  alias[label="@champion", shape=ellipse, fillcolor="{theme.CHAMPION}", fontcolor="white", color="{theme.CHAMPION}"];
  api  [label="API\\n/predict", fillcolor="{theme.TEAM_FILL}", color="#56606b"];
  code -> run; env -> run; data -> run;
  run -> ver -> alias -> api;
}}
"""
st.graphviz_chart(LINEAGE, width="stretch")

st.markdown(
    """
| Quoi | Comment | Pourquoi ce choix |
|---|---|---|
| **Code** | param `git_commit` (ou `GIT_COMMIT` injecté au build) | git est déjà la référence ; zéro outil en plus |
| **Données** | param `data_hash` = SHA-256 des matrices d'entraînement, `n_rows`, tags `date_min/max` ; snapshots parquet immuables | empreinte exacte **sans dupliquer** les données (pas de DVC à opérer) |
| **Environnement** | `uv.lock` → `requirements.txt` (`make lock`), images Docker | versions figées, installation reproductible |
| **Modèle** | Model Registry : une version par run, alias `@champion` | qui est servi, et depuis quand |
"""
)

runs, err = da.get_mlflow_runs()
theme.stop_on(err, "La table des runs s'affiche quand MLflow est démarré.", level="info")

st.subheader("Registre des runs : la preuve")
cols = [c for c in ("run_no", "start_time", "git_commit", "data_hash", "n_rows", "date_max",
                    "mae_valid", "run_id") if c in runs.columns]
st.dataframe(runs.select(cols).sort("run_no", descending=True).to_pandas(), width="stretch",
             hide_index=True,
             column_config={"mae_valid": st.column_config.NumberColumn(format="%.0f"),
                            "start_time": st.column_config.DatetimeColumn(format="DD/MM HH:mm")})

by_data = (runs.lazy().group_by("data_hash")
           .agg(pl.len().alias("runs"), pl.col("n_rows").first(), pl.col("mae_valid").min().alias("meilleure MAE"),
                pl.col("git_commit").n_unique().alias("commits"))
           .sort("runs", descending=True).collect())
c1, c2, c3 = st.columns(3)
c1.metric("Runs", runs.height)
c2.metric("Commits distincts", runs.get_column("git_commit").n_unique())
c3.metric("Jeux de données distincts", by_data.height)
with st.expander("Runs regroupés par jeu de données (data_hash)"):
    st.dataframe(by_data.to_pandas(), width="stretch", hide_index=True)
    st.caption("Même `data_hash` ⇒ mêmes données exactes : on compare alors des changements de **code**. "
               "`data_hash` différent ⇒ l'écart de MAE peut venir des **données** (année ajoutée par Airflow).")

unknown = runs.filter(pl.col("git_commit").is_null() | (pl.col("git_commit") == "unknown")).height
if unknown:
    st.warning(f"{unknown} run(s) sans commit identifié : lancés dans un conteneur où `GIT_COMMIT` "
               "n'est pas injecté au build — correction listée dans les next steps.")

theme.conclusion(
    "le run MLflow est le **point de jonction** : depuis la version servie on remonte au "
    "commit, à l'empreinte des données et à la MAE — sans outil supplémentaire à opérer."
)
theme.speaker_notes("versioning")
