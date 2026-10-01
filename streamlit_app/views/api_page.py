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
    "Prédire une valeur **immédiatement**, avec le champion MLflow du moment — sans "
    "redémarrer le conteneur et sans copier de fichier d'une brique à l'autre.",
    "L'API charge `models:/anomalies_conso_national@champion` au démarrage, puis garde le "
    "modèle **en mémoire**. Quand Airflow termine un entraînement, un `POST /reload` suffit "
    "à changer de version. Prometheus scrape le même `/metrics`.",
)

with st.expander("Pourquoi ces choix d'infrastructure ?", expanded=False):
    st.markdown(
        """
| Choix | Pourquoi |
|---|---|
| **Modèle en mémoire** (`model_state`) | l'inférence ne relit pas le registre à chaque requête ; changer de version revient à remplacer un objet Python |
| **`/reload` plutôt qu'un redémarrage** | redémarrer le conteneur interromprait le service et ferait recharger le modèle au démarrage ; on veut l'éviter à chaque run du DAG |
| **Promotion décidée par MLflow** | l'API ne choisit pas son modèle : elle suit l'alias `@champion`. Une seule source de vérité |
| **`/train` en tâche de fond** | la route répond `202` tout de suite, et refuse une nouvelle demande (`409`) si un entraînement est déjà en cours |
| **Conteneur non-root** (`appuser`, uid 1000) | l'API n'a rien à écrire dans l'image ; inutile de lui donner plus de droits |
| **Healthcheck sur `/verify`** | la route la plus légère possible : `depends_on: service_healthy` peut ainsi démarrer sans attendre le modèle |
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
        "Table lue dans `/openapi.json` : c'est le contrat que l'API sert réellement, "
        "et non une liste écrite à la main dans la documentation. Seules `/train` et "
        "`/reload` exigent le rôle `admin` — ce sont les deux routes qui modifient "
        "l'état du service."
    )

# -----------------------------------------------------------------------------
st.subheader("Le champion, en mémoire")
left, right = st.columns([3, 2])
left.markdown(
    """
Un dictionnaire `model_state` retient le modèle, sa version et son artefact. Trois
moments le font changer :

| Moment | Effet |
|---|---|
| **Démarrage** (`lifespan`) | `load_best_model()` lit l'alias `@champion` dans le registre |
| **Chaque `/predict`** | `score()` applique l'artefact en mémoire — aucun appel réseau |
| **`/reload`** (fin de DAG) | même chargement ; la réponse indique la version quittée et la version rejointe |
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
st.caption("Sans redémarrage : changer de modèle prend quelques secondes. C'est la tâche "
           "`reload_api`, en fin de DAG, qui appelle `/reload`.")

# -----------------------------------------------------------------------------
st.subheader("Authentification")
a1, a2 = st.columns(2)
a1.markdown(
    """
* Table `users` (créée et amorcée par `src/data/create_users.py`) : deux rôles, `user` et `admin`.
* Mots de passe **jamais stockés en clair** : `HMAC-SHA256(clé, mot de passe)`, puis comparaison à temps constant.
* `POST /token` renvoie un **JWT HS256** valable 60 minutes, qui porte `sub` et `role`.
* `require_admin` est une dépendance FastAPI : on la déclare sur la route, elle n'est pas écrite dans la fonction.
"""
)
a2.markdown(
    """
```python
@app.post("/reload", status_code=200,
          dependencies=[Depends(require_admin)])
def reload_model(): ...
```

Airflow suit exactement le même chemin : `POST /token`, puis
`POST /reload` avec l'en-tête `Authorization: Bearer …`.
"""
)

# -----------------------------------------------------------------------------
st.subheader("Détection de dérive, dans l'API même")
d1, d2 = st.columns([3, 2])
d1.markdown(
    """
Le service qui reçoit les données est le mieux placé pour surveiller si elles changent.
L'API garde les **5 dernières lignes reçues** dans un buffer et les compare aux **500
dernières lignes de référence**, feature par feature, avec un test de Kolmogorov–Smirnov.
Une p-value < 0,05 signifie que la distribution de la feature a bougé : c'est un signal
de dérive.
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
st.caption("Le calcul part **après** l'envoi de la réponse : l'appelant de `/predict` "
           "n'attend jamais le test statistique.")

theme.conclusion(
    "l'API est un **interchangeur mince** — elle ne réentraîne pas, ne décide pas, ne "
    "copie pas de fichier. Elle applique en mémoire le champion désigné par MLflow, et "
    "`/reload` suffit à le remplacer."
)

c1, c2 = st.columns(2)
c1.link_button("Ouvrir la doc Swagger ↗", da.service_urls()["api"] + "/docs", width="stretch")
c2.link_button("Voir /metrics (Prometheus) ↗",
               da.service_urls()["api"] + "/metrics", width="stretch")
theme.speaker_notes("api")
