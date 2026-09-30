"""Airflow — orchestration du ré-entraînement."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("airflow")
theme.header("Airflow", m["minutes"], m["owner"])

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

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=False):
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

# -----------------------------------------------------------------------------
st.subheader("Le DAG retrain_eco2mix")
st.graphviz_chart(
    f"""
digraph {{
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12,
        fillcolor="{theme.MINE_FILL}", color="{theme.REEL}"];
  edge [color="{theme.NEUTRE}"];
  ingest -> build_raw -> train -> reload_api;
  node [fillcolor="{theme.TEAM_FILL}", color="{theme.NEUTRE}", style="rounded,filled,dashed"];
  mlflow [label="MLflow\\n@champion"];
  api [label="API FastAPI"];
  train -> mlflow [style=dashed, label=" run + _promote_if_better", fontsize=10];
  reload_api -> api [style=dashed, label=" POST /reload", fontsize=10];
}}
""",
    width="stretch",
)
st.markdown(
    """
| Tâche | Ce qu'elle fait |
|---|---|
| `ingest` | charge les données ODRÉ jusqu'à l'année du curseur, dans `staging` |
| `build_raw` | type les données (`staging` → `raw`) |
| `train` | entraîne, logue le run dans MLflow ; `_promote_if_better` déplace `@champion` si la MAE s'améliore |
| `reload_api` | `POST /token` puis `POST /reload` : l'API charge le champion, sans redémarrer (voir page API) |
"""
)

# -----------------------------------------------------------------------------
st.subheader("En ce moment")
k1, k2 = st.columns([1, 3])
year, y_err = da.get_max_year()
k1.metric("Curseur `max_year`", year if y_err is None else "—",
          help="Dernière année « arrivée ». Le prochain run en ajoutera une.")
runs, r_err = da.get_airflow_runs(limit=5)
if r_err:
    k2.warning(r_err)
else:
    icons = {"success": "✅ succès", "failed": "❌ échec", "running": "⏳ en cours",
             "queued": "⏸ en file"}
    k2.dataframe(
        [{"état": icons.get(r["state"], r["state"]),
          "déclenchement": "planifié" if r["run_type"] == "scheduled" else "manuel",
          "début": r["start"],
          "durée": f"{r['duration_s'] // 60} min {r['duration_s'] % 60:02d} s"
                   if r["duration_s"] is not None else "—"} for r in runs],
        width="stretch", hide_index=True,
    )
    k2.caption("Lu en direct dans l'API REST d'Airflow : les 5 derniers runs du DAG.")

# -----------------------------------------------------------------------------
st.subheader("Une tâche = un conteneur")
d1, d2 = st.columns([3, 2])
d1.markdown(
    """
Les tâches ne tournent pas **dans** Airflow : chacune lance un conteneur de l'image
applicative, sur le réseau de la stack. Airflow reste léger et n'installe aucune
bibliothèque ML : pas de conflit de versions, et le code exécuté est exactement
celui de l'API et du développement.

**Contrepartie assumée** : pour lancer ces conteneurs, Airflow accède au socket
Docker de l'hôte, ce qui équivaut à des droits root. C'est la première ligne des
Next steps (KubernetesPodOperator, ou proxy de socket filtré en attendant).
"""
)
d2.markdown(
    """
```python
# principe d'une tâche (simplifié)
DockerOperator(
    task_id="train",
    image=os.environ["TRAINER_IMAGE"],
    command="python -m src.models.train_model",
    network_mode=os.environ["APP_NETWORK"],
    retries=2,
)
```
"""
)

theme.conclusion(
    "Airflow **orchestre, il ne décide pas** : il enchaîne les étapes et relance ce qui échoue, "
    "mais la promotion reste dans le code, et l'API ne change de modèle que sur ordre du registre."
)

st.link_button("Ouvrir Airflow ↗", da.service_urls()["airflow"], width="stretch")
theme.speaker_notes("airflow")
