"""API FastAPI — servir le champion à jour, sans redémarrage ni copie de fichier."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import data_access as da  # noqa: E402  (seul point d'accès données)
from lib import plan, theme  # noqa: E402

m = plan.meta("api")
theme.header("API FastAPI", m["minutes"], m["owner"])

theme.story(
    "Faire Predire une valeur **immédiatement**, avec le champion MLflow du moment — "
    "sans redémarrer le conteneur et sans copier de fichier entre les briques.",
    "L'API charge `models:/anomalies_conso_national@champion` au démarrage puis garde le "
    "modèle **en mémoire** ; quand Airflow termine un entraînement, un `POST /reload` "
    "suffit à changer de version. Prometheus scrape le même `/metrics`.",
)

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=False):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **Modèle en mémoire** (`model_state`) | l'inférence ne relit pas le registre à chaque requête ; le changement de version est un simple remplacement d'objet Python |
| **`/reload` plutôt qu'un redémarrage** | Airflow redeploie l'API à chaque run, on veut éviter un coup de service et une nouvelle phase de chargement du modèle |
| **Promotion décidée par MLflow** | l'API ne choisit pas : elle obéit à l'alias. Une seule source de vérité |
| **Entraînement en `BackgroundTasks`** | `/train` renvoie `202` immédiatement et refuse une seconde fois (`409`) si un run est déjà en cours |
| **Conteneur non-root** (`appuser`, uid 1000) | l'API n'a aucun besoin d'écrire dans l'image ; on ne le lui donne pas |
| **Healthcheck sur `/verify`** | la route la plus légère possible, pour que `depends_on: service_healthy` ne depende pas du modèle |
"""
    )

# -----------------------------------------------------------------------------
st.subheader("Les routes")
routes, err = da.get_api_routes()
if err:
    st.info(err)
    st.caption("Contrat de référence, lu dans `src/models/main_api.py` :")
    st.dataframe(
        [
            {"method": "POST", "path": "/token", "secured": False, "role": "—"},
            {"method": "GET", "path": "/verify", "secured": False, "role": "—"},
            {"method": "POST", "path": "/train", "secured": True, "role": "admin"},
            {"method": "POST", "path": "/predict", "secured": False, "role": "—"},
            {"method": "POST", "path": "/reload", "secured": True, "role": "admin"},
            {"method": "GET", "path": "/metrics", "secured": False, "role": "—"},
        ],
        width="stretch", hide_index=True,
    )
else:
    st.dataframe(
        [{"méthode": r["method"], "chemin": f"`{r['path']}`", "résumé": r["summary"],
          "droits requis": "🔑 admin" if r["secured"] else "—"} for r in routes],
        width="stretch", hide_index=True,
    )
    st.caption(
        "Table lue dans `/openapi.json` : c'est le contrat que l'API sert "
        "réellement, pas une liste-maintenance. Les seules routes à privilèges sont "
        "`/train` et `/reload` — celles qui modifient l'état du service."
    )

# -----------------------------------------------------------------------------
st.subheader("Le champion, en mémoire")
left, right = st.columns([3, 2])
left.markdown(
    """
Un dictionnaire `model_state` tient le modèle, sa version et son artefact. Trois
moments le font vivre :

| Moment | Effet |
|---|---|
| **Démarrage** (`lifespan`) | `load_best_model()` lit l'alias `@champion` dans le registre |
| **Chaque `/predict`** | `score()` applique l'artefact en mémoire — aucun appel réseau |
| **`/reload`** (fin de DAG) | même chargement, et la réponse dit ce qu'on quitte et ce qu'on rejoint |
"""
)
right.markdown(
    f"""
    <div style="border:1px solid {theme.NEUTRE}33; border-radius:8px; padding:12px 14px;">
    <div style="color:{theme.NEUTRE}; font-size:13px; margin-bottom:6px;">POST /reload</div>
    <code style="font-size:13px;">{{<br>
&nbsp;&nbsp;"old_model": "anomalies_conso_national:3",<br>
&nbsp;&nbsp;"new_model": "anomalies_conso_national:4"<br>
}}</code>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Sans redémarrage : le changement de modèle est une opération de quelques secondes, "
           "appelée par la tâche `reload_api` à la fin du DAG.")

# -----------------------------------------------------------------------------
st.subheader("Authentification")
a1, a2 = st.columns(2)
a1.markdown(
    """
* Table `users` (créée et amorcée par `src/data/create_users.py`) : deux rôles, `user` et `admin`.
* Mots de passe **jamais stockés en clair** : `HMAC-SHA256(clé, mot de passe)`, comparaison à temps constant.
* `POST /token` renvoie un **JWT HS256** valable 60 minutes, qui porte `sub` et `role`.
* `require_admin` est une dépendance FastAPI : elle s'ajoute à une route, elle ne se code pas dans sa fonction.
"""
)
a2.markdown(
    """
```python
@app.post("/reload", status_code=200,
          dependencies=[Depends(require_admin)])
def reload_model(): ...
```

Airflow fait exactement le même chemin : `POST /token` puis
`POST /reload` avec l'en-tête `Authorization: Bearer …`.
"""
)

# -----------------------------------------------------------------------------
st.subheader("Détection de dérive, dans l'API même")
d1, d2 = st.columns([3, 2])
d1.markdown(
    """
Le service qui reçoit les données est le meilleur endroit pour surveiller si elles
bougent. L'API garde les **5 dernières lignes** reçues dans un buffer, et les compare
aux **500 dernières lignes de référence** par un test de Kolmogorov–Smirnov, feature
par feature. Une p-value < 0,05 est un signal de dérive.
"""
)
d2.markdown(
    f"""
    <div style="border:1px solid {theme.NEUTRE}33; border-radius:8px; padding:12px 14px;">
    <div style="color:{theme.NEUTRE}; font-size:13px; margin-bottom:8px;">Gauges exposées</div>
    <code style="font-size:13px;">model_feature_drift_ks_pvalue{{feature}}</code><br>
    <code style="font-size:13px;">model_drifted_features_ratio</code><br>
    <code style="font-size:13px;">model_prediction_mean</code>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Le calcul part en tâche de fond après la réponse : "
           "`/predict` ne paie jamais le test statistique.")

theme.conclusion(
    "l'API est un **inter Exchangeur mince** — elle ne réentraîne pas, ne décide pas, "
    "ne copie pas : elle applique en mémoire le champion désigné par MLflow, et `/reload` "
    "suffit à le remplacer."
)

c1, c2 = st.columns(2)
c1.link_button("Ouvrir la doc Swagger ↗", da.service_urls()["api"] + "/docs", width="stretch")
c2.link_button("Voir /metrics (Prometheus) ↗",
               da.service_urls()["api"] + "/metrics", width="stretch")
theme.speaker_notes("api")
