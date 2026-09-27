"""Plan de la soutenance (conseillé par le mentor) + budget temps.

20 min = 15 min de présentation + 5 min de démo, puis 10 min de questions.
Les parties « Ludo » totalisent 5 min (contexte + MLflow + versioning).
"""

from __future__ import annotations

ME = "Ludo"
TEAM = "Équipe"
TBD = "coéquipier"

## (clé, fichier, titre, icône, minutes, orateur, section)
# (clé, fichier, titre, minutes, orateur, section)
PLAN = [
    ("contexte", "views/contexte.py", "Contexte & modèle maison", "🎯", 2.25, ME, "Présentation"),
    ("architecture", "views/architecture.py", "Architecture", "🗺️", 1.5, TEAM, "Présentation"),
    ("bdd", "views/bdd_page.py", "Base de données", "🗄️", 1.5, TBD, "Composants"),
    ("api", "views/api_page.py", "API FastAPI", "🔌", 1.5, TBD, "Composants"),
    ("mlflow", "views/mlflow_page.py", "MLflow", "🧪", 1.5, ME, "Composants"),
    ("versioning", "views/versioning.py", "Versioning", "🔖", 1.25, ME, "Composants"),
    ("airflow", "views/airflow_page.py", "Airflow", "🌀", 1.5, TBD, "Composants"),
    ("grafana", "views/grafana_page.py", "Prometheus & Grafana", "📡", 1.0, TBD, "Composants"),
    ("streamlit", "views/streamlit_page.py", "Streamlit", "🖥️", 1.0, ME, "Composants"),
    ("demo", "views/demo.py", "Démo live", "▶️", 5.0, TEAM, "Démo"),
    ("next", "views/next_steps.py", "Next steps", "🚀", 1.5, TEAM, "Suite"),
    ("conclusion", "views/conclusion.py", "Conclusion", "✅", 0.5, TEAM, "Suite"),
]

_BY_KEY = {p[0]: p for p in PLAN}


def meta(key: str) -> dict:
    k, f, title, icon, minutes, owner, section = _BY_KEY[key] 
    return {"key": k, "file": f, "title": title, "icon": icon, "minutes": minutes, #
            "owner": owner, "section": section}


def total(section: str | None = None, owner: str | None = None) -> float:
    return sum(p[4] for p in PLAN
               if (section is None or p[6] == section) and (owner is None or p[5] == owner))
