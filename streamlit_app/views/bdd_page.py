"""Base de données — une source unique, traçable et reproductible."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("bdd")
theme.header("Base de données", m["minutes"], m["owner"])


def _n(x: int) -> str:
    """12345678 -> '12 345 678' (espace fine insécable)."""
    return f"{x:,}".replace(",", "\u202f")


theme.story(
    "Répondre à tout moment à deux questions : **d'où vient chaque donnée** "
    "(et quelles transformations elle a subies) et **sur quel jeu exact un modèle "
    "a été entraîné**, avec une seule source de vérité partagée par tous les services.",
    "Les données ODRÉ sont chargées en masse (`COPY`, via `src.data.load`) dans `staging`, "
    "typées dans `raw` (`src.data.build_raw`), puis nettoyées dans `clean`. "
    "Le schéma est versionné par **Alembic**. `make snapshot` fige un jeu de données "
    "en **parquet immuable** qui sert de référence à l'entraînement. "
    "MLflow et Airflow ont chacun **leur base et leur rôle** (`make db-meta`).",
)

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=False):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **PostgreSQL 16** conteneurisé | robuste, SQL standard, déjà requis par MLflow et Airflow : une seule techno à maintenir |
| Schémas `staging` → `raw` → `clean` | chaque transformation est traçable ; on rejoue une couche sans recharger ODRÉ |
| `COPY` plutôt qu'`INSERT` | chargement en masse, adapté au volume des 4 jeux éCO2mix |
| Migrations **Alembic** | le schéma évolue avec le code, rejouable sur n'importe quel poste |
| **Snapshots parquet** immuables | un entraînement pointe un jeu figé : résultats reproductibles même si la base évolue |
| Bases et **rôles dédiés** `mlflow` / `airflow` | moindre privilège : un service compromis n'accède pas aux données métier |
| Healthcheck `pg_isready` | l'API, MLflow et Airflow ne démarrent qu'une fois la base prête |
| Volume `pgdata` | données persistantes entre les redémarrages des conteneurs |
"""
    )

# -----------------------------------------------------------------------------
st.subheader("La base, en ce moment")
overview, err = da.get_db_overview()
if err:
    st.error(err)
    st.caption("Démarrer la base : `docker compose up -d db`.")
else:
    tables = overview["tables"]
    cols = st.columns(4)
    for col, layer in zip(cols, da.DB_LAYERS):
        layer_tables = [t for t in tables if t["couche"] == layer]
        rows = sum(t["lignes"] for t in layer_tables)
        col.metric(f"Couche {layer}", _n(rows) if layer_tables else "—",
                   help=f"{len(layer_tables)} table(s)")
    summary, s_err = da.get_features_summary()
    if s_err is None:
        cols[3].metric("Période couverte",
                       f"{summary['date_min']:%Y} → {summary['date_max']:%Y}",
                       help=f"{_n(summary['n_rows'])} lignes de features")
    else:
        cols[3].metric("Révision Alembic", overview["alembic"] or "—")
    st.caption(
        "Lignes estimées par les statistiques de PostgreSQL (`pg_stat_user_tables`), "
        "pas un `COUNT(*)` : la page reste instantanée quel que soit le volume."
        + (f" Révision Alembic : `{overview['alembic']}`." if overview["alembic"] else "")
    )
    with st.expander("Détail par table"):
        st.dataframe(tables, width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
st.subheader("Trois couches, trois rôles")
left, right = st.columns([3, 2])
# TODO équipe : vérifier que la ligne `clean` décrit bien ce que fait le code.
left.markdown(
    """
| Couche | Contenu | Produit par |
|---|---|---|
| `staging` | les données telles que publiées par ODRÉ, sans transformation | `src.data.load` (`COPY`) |
| `raw` | les mêmes données, **typées** (dates, numériques) | `src.data.build_raw` |
| `clean` | données nettoyées et dédoublonnées, prêtes pour les features | pipeline de nettoyage |

Une donnée n'est jamais modifiée sur place : en cas d'erreur, on rejoue la couche
fautive à partir de la précédente, sans retélécharger ODRÉ.
"""
)
right.markdown(
    """
```python
# principe du chargement (simplifié)
with cur.copy(
    "COPY staging.<table> FROM STDIN "
    "(FORMAT csv, HEADER)"
) as copy:
    for bloc in fichier:
        copy.write(bloc)
```
Un flux unique par fichier, au lieu d'un `INSERT` par ligne.
"""
)

# -----------------------------------------------------------------------------
st.subheader("Une base par service, un rôle par base")
c1, c2 = st.columns([3, 2])
c1.markdown(
    """
MLflow et Airflow ont besoin d'une base pour leurs **métadonnées**. Plutôt que de
leur ouvrir la base métier, `make db-meta` crée pour chacun **sa base et son rôle** :

* le rôle `mlflow` ne voit que la base `mlflow`, le rôle `airflow` que la base `airflow` ;
* un service compromis n'a **aucun accès** aux données éCO2mix ;
* chaque service reçoit uniquement ses propres identifiants.
"""
)
if err is None:
    c1.dataframe(overview["databases"], width="stretch", hide_index=True)
    c1.caption("Lu en direct dans `pg_database` : chaque base appartient à son service.")
c2.markdown(
    """
```sql
-- principe de make db-meta
CREATE ROLE mlflow LOGIN PASSWORD '…';
CREATE DATABASE mlflow OWNER mlflow;

CREATE ROLE airflow LOGIN PASSWORD '…';
CREATE DATABASE airflow OWNER airflow;
```
"""
)

# -----------------------------------------------------------------------------
st.subheader("Figer un jeu : les snapshots")
s1, s2 = st.columns([2, 3])
s1.markdown(
    """
La base évolue à chaque exécution du DAG. Pour qu'un entraînement reste
**reproductible**, `make snapshot` fige un jeu de données en **parquet immuable** :
on peut toujours ré-entraîner sur exactement les mêmes lignes, et comparer deux
modèles à données égales.
"""
)
snapshots, snap_err = da.get_snapshots()
if snap_err:
    s2.info(snap_err)
else:
    s2.dataframe(snapshots, width="stretch", hide_index=True)

theme.conclusion(
    "la base est le **socle** du projet : chaque transformation est traçable couche par couche, "
    "chaque entraînement pointe un jeu figé, et chaque service n'accède qu'à ce qui le concerne."
)

theme.speaker_notes("bdd")
