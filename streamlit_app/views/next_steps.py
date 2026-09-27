"""Next steps — corrections, améliorations, techno, Kubernetes, CI/CD, sécurité."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import plan, theme  # noqa: E402

m = plan.meta("next")
theme.header("Next steps", m["minutes"], m["owner"])
st.caption("Brouillon construit à partir d'une relecture du repo — à trier en équipe. "
           "Priorité : 🔴 avant toute mise en production · 🟠 prochaine itération · 🟢 plus tard.")

tabs = st.tabs(["Corrections", "Améliorations", "Techno", "Kubernetes", "CI/CD",
                "Cyber · durcissement · cloisonnement"])

with tabs[0]:
    st.markdown(
        """
| Action | Constat | Priorité |
|---|---|---|
| Sortir la clé JWT du code | `SECRET_KEY` écrite en dur dans `src/models/main_api.py` | 🔴 |
| Hacher les mots de passe avec bcrypt / argon2 | HMAC-SHA256 avec la même clé fixe dans `create_users.py` | 🔴 |
| Changer les identifiants par défaut | Grafana `admin/admin` dans le compose ; compte API `admin/admin` du seed | 🔴 |
| Injecter le commit dans l'image | pas d'`ARG GIT_COMMIT` dans le Dockerfile → runs Airflow avec `git_commit=unknown` | 🟠 |
| Un seul nom de modèle | `MODEL_NAME` / `MODEL_ALIAS` redéclarés dans l'API au lieu de lire `settings` | 🟠 |
| Nettoyer le README | reste du template « movie_recommandation » | 🟢 |
"""
    )

with tabs[1]:
    st.markdown(
        """
| Action | Pourquoi | Priorité |
|---|---|---|
| Métriques **métier** exposées à Prometheus | taux d'anomalies, version servie, MAE glissante — pas seulement la latence HTTP | 🟠 |
| **Détection de dérive** (ex. Evidently) | savoir *quand* réentraîner plutôt que tous les jours à 4 h | 🟠 |
| Validation des données à l'ingestion | schéma + bornes (ex. pandera sur polars) avant `build_raw` | 🟠 |
| Évaluation sur **événements connus** | confinement 2020, vagues de froid : mesurer rappel / fausses alertes, calibrer *k* | 🟢 |
| Alertes Grafana | notifier au lieu de regarder un tableau | 🟢 |
"""
    )

with tabs[2]:
    st.markdown(
        """
| Piste | Intérêt |
|---|---|
| Modèles concurrents dans le même pipeline (linéaire, LightGBM, quantiles) | la règle `@champion` les départage sans changer l'API |
| Seuil *k* dynamique / par régime (été, hiver, fériés) | moins de fausses alertes saisonnières |
| Flux temps réel éCO2mix (pas 15 min) | déjà prévu par `ANOM_FREQ=15m` |
| MLflow Model Serving ou BentoML | comparer au service FastAPI maison |
"""
    )

with tabs[3]:
    st.markdown(
        """
| Brique | Cible Kubernetes |
|---|---|
| API | `Deployment` + `HorizontalPodAutoscaler`, `readinessProbe` sur `/verify` |
| Airflow | chart Helm officiel, **KubernetesPodOperator** au lieu du DockerOperator (plus de montage du socket Docker) |
| PostgreSQL | opérateur (ex. CloudNativePG) : sauvegardes, réplicas |
| Silo / MLflow | `StatefulSet` + volumes persistants ; MLflow en `Deployment` |
| Monitoring | kube-prometheus-stack |
| Secrets | `Secret` K8s alimentés par un coffre (Vault, SOPS) |
"""
    )

with tabs[4]:
    st.markdown(
        """
| Étape | Aujourd'hui | Cible |
|---|---|---|
| Installation | `pip install -r requirements.txt` | `uv sync --frozen` (même lock qu'en local) |
| Qualité | flake8 + pytest | ruff + pytest avec couverture, tests d'intégration compose |
| Build | — | build des images + scan (ex. Trivy) + SBOM |
| Publication | — | push sur un registre (GHCR) avec tag = commit |
| Déploiement | manuel (`make up`) | déploiement sur tag ; entraînement de contrôle comparé au champion |
"""
    )

with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Déjà en place ✓**")
        st.markdown(
            """
- un **rôle PostgreSQL par service** (métier, mlflow, airflow)
- clés S3 connues du **seul** conteneur MLflow (`--serve-artifacts`)
- API S3 de Silo **interne** au réseau ; console liée à `127.0.0.1`
- utilisateur applicatif Silo limité au bucket `mlflow`
- API en utilisateur **non-root**, routes `/train` et `/reload` réservées aux admins (JWT)
"""
        )
    with c2:
        st.markdown("**À faire**")
        st.markdown(
            """
- 🔴 secrets hors du code et des fichiers en clair (Docker secrets, Vault, SOPS)
- 🔴 ne plus monter `/var/run/docker.sock` dans Airflow (équivaut à root sur l'hôte)
- 🟠 réseaux séparés front / back ; ne plus publier PostgreSQL sur l'hôte
- 🟠 reverse proxy **TLS** (Traefik / Caddy) devant API, MLflow, Grafana, Airflow
- 🟠 authentification sur `/predict` + limitation de débit
- 🟢 épingler les images par digest (`silo`, `prometheus`, `grafana` en `latest`)
"""
        )

theme.speaker_notes("next")
