"""Airflow — partie coéquipier (cadre à compléter)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402,F401  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("airflow")
theme.header("Airflow", m["minutes"], m["owner"])
#theme.stub("responsable de l'orchestration", ['DAG `retrain_eco2mix`, quotidien 4 h : `ingest → build_raw → train → reload_api`', "**DockerOperator** : chaque tâche tourne dans l'image applicative (pas de dépendances ML dans Airflow)", "Pas de tâche de promotion : c'est MLflow (`_promote_if_better`) qui décide → une seule source de vérité", 'Curseur `max_year.conf` : une année de plus à chaque exécution (arrivée de données simulée)', "Fichier compose séparé + profil `airflow` (n'impacte pas `make up`)", '`max_active_runs=1`, 2 retries, timeouts par tâche'])

theme.story(
    "**Ré-entraîner automatiquement** le modèle à mesure que les données arrivent, "
    "sans intervention manuelle, et **sans qu'un run raté ne dégrade la production**.",
    "Le DAG `retrain_eco2mix` tourne chaque jour à 4 h et enchaîne "
    "`ingest` → `build_raw` → `train` → `reload_api`. Chaque tâche s'exécute via "
    "**DockerOperator** dans l'image applicative. Airflow ne promeut rien lui-même : "
    "c'est `_promote_if_better` qui déplace `@champion`, et `reload_api` recharge "
    "le champion courant. Le curseur `max_year.conf` ajoute une année à chaque "
    "exécution pour simuler l'arrivée de nouvelles données.",
)

#st.divider()

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=True):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **Airflow** | orchestrateur standard : planification, UI de suivi, historique des runs, retries intégrés |
| DAG linéaire `ingest` → `build_raw` → `train` → `reload_api` | une étape ne démarre que si la précédente a réussi ; un échec est localisé et relançable seul |
| **DockerOperator** | aucune dépendance ML dans Airflow : mêmes versions de libs qu'en dev, pas de conflits |
| **Pas de tâche de promotion** | une seule source de vérité : Airflow orchestre, le code décide (voir page MLflow) |
| `reload_api` systématique | sans nouveau champion, l'API recharge le même modèle : sans risque, et toujours à jour sinon |
| Curseur `max_year.conf` | simule l'arrivée de données sur un historique : on voit le modèle évoluer run après run |
| `max_active_runs=1` | jamais deux ré-entraînements concurrents sur la même base et le même registre |
| 2 retries + timeouts par tâche | absorbe les erreurs transitoires ; une tâche bloquée ne gèle pas le DAG |
| Compose séparé + profil `airflow` | Airflow est lourd (scheduler, webserver…) : `make up` reste rapide pour le reste de la stack |
| Base et rôle `airflow` dédiés | métadonnées isolées des données métier (moindre privilège, voir page BDD) |
"""
    )

st.caption(
    "DAG `retrain_eco2mix` · planification quotidienne 4 h · "
    "Démarrer : `make airflow`"
)

# theme.speaker_notes("airflow")
st.link_button("Ouvrir Airflow ↗", da.service_urls()["airflow"])
theme.speaker_notes("airflow")
