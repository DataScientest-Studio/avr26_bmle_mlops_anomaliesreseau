Project Name
==============================

This project is a starting Pack for MLOps projects based on the subject "movie_recommandation". It's not perfect so feel free to make some modifications on it.

Project Organization
------------

    ├── LICENSE
    ├── README.md          <- The top-level README for developers using this project.
    ├── data
    │   ├── external       <- Data from third party sources.
    │   ├── interim        <- Intermediate data that has been transformed.
    │   ├── processed      <- The final, canonical data sets for modeling.
    │   └── raw            <- The original, immutable data dump.
    │
    ├── logs               <- Logs from training and predicting
    │
    ├── models             <- Trained and serialized models, model predictions, or model summaries
    │
    ├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),
    │                         the creator's initials, and a short `-` delimited description, e.g.
    │                         `1.0-jqp-initial-data-exploration`.
    │
    ├── references         <- Data dictionaries, manuals, and all other explanatory materials.
    │
    ├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.
    │   └── figures        <- Generated graphics and figures to be used in reporting
    │
    ├── requirements.txt   <- The requirements file for reproducing the analysis environment, e.g.
    │                         generated with `pip freeze > requirements.txt`
    │
    ├── src                <- Source code for use in this project.
    │   ├── __init__.py    <- Makes src a Python module
    │   │
    │   ├── data           <- Scripts to download or generate data
    │   │   └── make_dataset.py
    │   │
    │   ├── features       <- Scripts to turn raw data into features for modeling
    │   │   └── build_features.py
    │   │
    │   ├── models         <- Scripts to train models and then use trained models to make
    │   │   │                 predictions
    │   │   ├── predict_model.py
    │   │   └── train_model.py
    │   │
    │   ├── visualization  <- Scripts to create exploratory and results oriented visualizations
    │   │   └── visualize.py
    │   └── config         <- Describe the parameters used in train_model.py and predict_model.py

--------

<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>

MLflow — suivi d'expériences & versioning
------------

Chaque entraînement est **loggé** dans MLflow (params, métriques, artefacts) et le
modèle est **versionné** au Model Registry, avec promotion automatique d'un
**champion** (la version dont la MAE de validation est la plus basse). Le
`predict` sert **toujours le champion**, pas le dernier entraîné ; repli
automatique sur `models/model.joblib` si MLflow est indisponible.

**Lancer**

```bash
docker compose up -d db mlflow          # Postgres + serveur MLflow (UI: http://localhost:5000)
export MLFLOW_TRACKING_URI=http://localhost:5000
uv run python -m src.models.train_model     # → un run + une version dans MLflow
uv run python -m src.models.predict_model --save
```

Sans `MLFLOW_TRACKING_URI`, MLflow est désactivé (on garde le joblib local).

**Configuration** (variables d'environnement)

| Variable | Rôle | Défaut |
|---|---|---|
| `MLFLOW_TRACKING_URI` | serveur MLflow ; vide = désactivé | — |
| `ANOM_MLFLOW_EXPERIMENT` | nom d'expérience | `anomalies_conso` |
| `ANOM_MLFLOW_MODEL_NAME` | modèle enregistré | `anomalies_conso_national` |
| `ANOM_MLFLOW_CHAMPION_ALIAS` | alias du meilleur modèle | `champion` |

Back-end MLflow = base `mlflow` sur le PostgreSQL du projet (créée au démarrage du
service) ; artefacts sur le volume `mlartifacts`. Après ajout de `mlflow` aux
dépendances : `uv sync` puis `make lock`.
