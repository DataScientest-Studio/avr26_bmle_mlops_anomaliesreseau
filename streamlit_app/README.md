# App Streamlit de soutenance

Démo « architecture d'abord » du projet de détection d'anomalies sur la
consommation électrique nationale (éCO2mix / RTE).

Navigation (`st.navigation`) calquée sur le plan conseillé par le mentor ;
chaque page affiche son budget temps et son orateur. Plan et budgets : `lib/plan.py`.

| Section | Page (`views/`) | Orateur | Budget |
|---|---|---|---|
| Présentation | `contexte.py` — contexte + modèle maison | Ludo | 2 min 15 |
| | `architecture.py` — schéma d'ensemble + état des services | équipe | 1 min 30 |
| Composants | `bdd_page.py` — *cadre à compléter* | coéquipier | 1 min 30 |
| | `api_page.py` — *cadre à compléter* | coéquipier | 1 min 30 |
| | `mlflow_page.py` — champion, courbe MAE, versions | Ludo | 1 min 30 |
| | `versioning.py` — code / données / env / modèle, table des runs | Ludo | 1 min 15 |
| | `airflow_page.py` — *cadre à compléter* | coéquipier | 1 min 30 |
| | `grafana_page.py` — *cadre à compléter* | coéquipier | 1 min |
| | `streamlit_page.py` — conception de l'app | Ludo | 1 min |
| Démo | `demo.py` — réel vs prédit, slider *k*, liens vers les UIs | équipe | 5 min |
| Suite | `next_steps.py` — corrections, améliorations, K8s, CI/CD, sécurité | équipe | 1 min 30 |
| | `conclusion.py` | équipe | 30 s |

Total : 15 min de présentation + 5 min de démo (+ 10 min de questions).

**Notes orateur** : `NOTES_ORATEUR.md` (texte oral des parties Ludo). Chaque section
s'affiche sous la page correspondante quand on active « 🎤 Notes orateur » dans la
barre latérale. Pour ajouter des notes à une autre page : une section
`<!-- key: <clé de lib/plan.py> -->` dans le même fichier.

**Pages coéquipiers** : `theme.stub(...)` affiche un cadre objectif → comment →
conclusion ; remplacer l'appel par le contenu réel.

## Lancer

```bash
uv add streamlit
docker compose up -d            # ou make up
export MLFLOW_TRACKING_URI=http://localhost:5000
uv run streamlit run streamlit_app/app.py     # http://localhost:8501
```

`streamlit_app/.streamlit/config.toml` (0.0.0.0:8501) n'est lu que si l'on lance
**depuis `streamlit_app/`** (Streamlit lit la config du dossier courant). Depuis la
racine, passer les options explicitement :

```bash
uv run streamlit run streamlit_app/app.py --server.address 0.0.0.0 --server.port 8501
```

Cible Makefile suggérée :

```make
demo: ## App Streamlit de démo (http://localhost:8501)
	uv run streamlit run streamlit_app/app.py --server.address 0.0.0.0 --server.port 8501
```

Le `.env` de la racine est pré-chargé par `lib/data_access.py`, donc les deux modes
de lancement voient les mêmes identifiants PostgreSQL.

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `ANOM_APP_SOURCE` | `direct` (réutilise `src.*` + base + MLflow) ou `api` (squelette `_via_api`, non implémenté) | `direct` |
| `ANOM_SOURCE` | source des features pour `load_features()` : `db` ou `csv` | `db` |
| `MLFLOW_TRACKING_URI` | serveur MLflow | `settings.mlflow_tracking_uri` puis `http://localhost:5000` |
| `MLFLOW_UI_URL` | URL de l'UI MLflow pour le bouton (si différente de l'URI) | = URI |
| `ANOM_API_URL` / `ANOM_SILO_URL` / `ANOM_AIRFLOW_URL` / `ANOM_PROMETHEUS_URL` / `ANOM_GRAFANA_URL` | sondes et liens | `:8000` / `:9001` (console) / `:${AIRFLOW_PORT:-8080}` / `:9090` / `:3000` |

## Conception

- **`lib/data_access.py` est le seul point d'accès données.** Les pages n'importent
  jamais `src.*`. Le module ajoute la racine du repo à `sys.path`, importe `src.*`
  paresseusement, et chaque fonction renvoie `(donnée, erreur)` : si un service est
  éteint, la page affiche le message et s'arrête (`st.stop()`) au lieu de planter.
- Contrats réutilisés : `load_features()`, `resolve_artifact()` (champion MLflow,
  repli `models/model.joblib`), `score()`, `settings` (noms d'expérience/modèle/alias).
- Cache : `st.cache_resource` pour le modèle et le client MLflow, `st.cache_data`
  pour les features, le scoring (clé = version du modèle) et les lectures MLflow
  (TTL 30 s). Le bouton « Rafraîchir » de l'accueil vide les caches.
- Le client MLflow est configuré sans retries (`MLFLOW_HTTP_REQUEST_MAX_RETRIES=0`)
  et précédé d'un appel `/health` : un serveur éteint donne un message immédiat.
- **Graphiques Altair**, petites données uniquement : agrégation/filtre en polars
  (lazy) avant `.to_pandas()`, fenêtres plafonnées à 5 000 points.
- **Palette Okabe-Ito** (`lib/theme.py`) : réel `#0072B2`, prédit `#E69F00`,
  anomalie `#D55E00` (réservé à ce statut), week-end/férié `#009E73`, jour ouvré
  `#9aa0a6`, champion `#CC79A7`. Le prédit est aussi en pointillés (lisible en N&B).

## Tests

```bash
uv run pytest streamlit_app/tests   # AppTest headless, services éteints : 0 exception attendue
```

## Ajouter du contenu (coéquipiers)

1. Ajouter une fonction `get_xxx() -> (donnée, erreur)` dans `lib/data_access.py`
   (imports `src.*` dans la fonction, `try/except` → `(None, message)`).
2. Dans la page : `df, err = da.get_xxx()` puis `theme.stop_on(err)`.
3. Garder le format `theme.story(objectif, comment)` … `theme.conclusion(...)`.
