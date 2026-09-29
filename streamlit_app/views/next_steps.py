
"""Next steps — corrections, améliorations, techno, Kubernetes, CI/CD, sécurité."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import plan, theme  # noqa: E402

m = plan.meta("next")
theme.header("Next steps", m["minutes"], m["owner"])

# --- Synthèse : le message à retenir en 30 secondes ---------------------------
st.markdown("#### Si on ne devait faire que trois choses")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        "🔴 **Secrets et authentification**  \n"
        "Clé JWT hors du code, mots de passe en bcrypt/argon2, "
        "plus aucun identifiant par défaut, configuration Airflow non exposée."
    )
with c2:
    st.markdown(
        "🔴 **Supprimer l'accès au socket Docker**  \n"
        "Aujourd'hui, Airflow compromis = hôte compromis. "
        "Cible : KubernetesPodOperator."
    )
with c3:
    st.markdown(
        "🟠 **Ré-entraîner sur dérive, pas sur horaire**  \n"
        "Métriques métier dans Prometheus + détection de dérive "
        "pour déclencher le DAG quand c'est utile."
    )

st.caption("Priorité : 🔴 avant toute mise en production · 🟠 prochaine itération · 🟢 plus tard.")
st.divider()

tabs = st.tabs(["Corrections", "Améliorations", "Techno", "Kubernetes", "CI/CD",
                "Cyber · durcissement · cloisonnement"])

with tabs[0]:
    st.markdown(
        """
| Action | Constat | Priorité |
|---|---|---|
| Sortir la clé JWT du code | `SECRET_KEY` écrite en dur dans `src/models/main_api.py` | 🔴 |
| Hacher les mots de passe avec bcrypt / argon2 | HMAC-SHA256 avec la même clé fixe dans `create_users.py` | 🔴 |
| Changer les identifiants par défaut | Grafana `admin/admin` dans le compose ; comptes API et Airflow `admin/admin` par défaut | 🔴 |
| Ne plus exposer la configuration Airflow | `EXPOSE_CONFIG=true` : mot de passe de la base et clé Fernet lisibles dans l'UI | 🔴 |
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
| Métriques **métier** exposées à Prometheus | taux d'anomalies, version servie, MAE glissante, pas seulement la latence HTTP | 🟠 |
| **Détection de dérive** (ex. Evidently) | savoir *quand* ré-entraîner plutôt que tous les jours à 4 h | 🟠 |
| Validation des données à l'ingestion | schéma + bornes (ex. pandera sur polars) avant `build_raw` | 🟠 |
| **Sauvegardes PostgreSQL** planifiées | `pg_dump` orchestré par Airflow, restauration testée | 🟠 |
| Procédure de **rollback** documentée | remettre `@champion` sur la version précédente : une commande, à écrire noir sur blanc | 🟠 |
| Évaluation sur **événements connus** | confinement 2020, vagues de froid : mesurer rappel / fausses alertes, calibrer *k* | 🟢 |
| Partitionnement par date (ou TimescaleDB) | le volume croît à chaque exécution | 🟢 |
| Alertes Grafana + logs centralisés (Loki) | être notifié au lieu de surveiller un tableau ; corréler les erreurs entre services | 🟢 |
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
| Airflow | chart Helm officiel, **KubernetesPodOperator** au lieu du DockerOperator (voir onglet Cyber) |
| PostgreSQL | opérateur (ex. CloudNativePG) : sauvegardes, réplicas |
| Silo / MLflow | `StatefulSet` + volumes persistants ; MLflow en `Deployment` |
| Monitoring | kube-prometheus-stack |
| Secrets | `Secret` K8s alimentés par un coffre (Vault, SOPS) |
| Cloisonnement | `NetworkPolicy` par service, `resources.limits` sur chaque pod |
"""
    )

with tabs[4]:
    st.markdown(
        """
| Étape | Aujourd'hui | Cible |
|---|---|---|
| Installation | `pip install -r requirements.txt` | `uv sync --frozen` (même lock qu'en local) |
| Qualité | flake8 + pytest | ruff + pytest avec couverture, tests d'intégration compose |
| Build | — | build multi-étapes (sans compilateurs ni `data/` dans l'image) + scan (ex. Trivy) + SBOM |
| Publication | — | push sur un registre (GHCR) avec tag = commit (corrige aussi `git_commit=unknown`) |
| Déploiement | manuel (`make up`) | déploiement sur tag ; entraînement de contrôle comparé au champion |
"""
    )

with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Déjà en place ✓**")
        st.markdown(
            """
- **tous les conteneurs en non-root** (API, PostgreSQL, MLflow, Silo, Airflow, Grafana, Prometheus), vérifié avec `docker top`
- un **rôle PostgreSQL par service** (métier, mlflow, airflow)
- clés S3 connues du **seul** conteneur MLflow (`--serve-artifacts`)
- API S3 de Silo **interne** au réseau ; console liée à `127.0.0.1`
- utilisateur applicatif Silo limité au bucket `mlflow`
- Silo ne reçoit **que ses propres identifiants** (pas d'`env_file` partagé)
- secrets passés en variables d'environnement, **pas en arguments** (invisibles dans un `ps`)
- MinIO remplacé par **Silo**, son fork maintenu (image amont retirée, plus de correctifs)
- routes `/train` et `/reload` réservées aux admins (JWT)
"""
        )
    with c2:
        st.markdown("**À faire**")
        st.markdown(
            """
- 🔴 gestion des secrets par un coffre (Docker secrets, Vault, SOPS), au-delà des corrections de l'onglet 1
- 🔴 ne plus monter `/var/run/docker.sock` dans Airflow (équivaut à root sur l'hôte) ; en attendant : proxy de socket filtré
- 🟠 réseaux séparés front / back ; ne plus publier PostgreSQL sur l'hôte
- 🟠 reverse proxy **TLS** (Nginx, Traefik ou Caddy) devant API, MLflow, Grafana, Airflow
- 🟠 authentification sur `/predict` + limitation de débit
- 🟠 épingler les images par digest (`silo`, `prometheus`, `grafana` en `latest`)
- 🟠 format de modèle sûr (skops) plutôt que pickle : charger un pickle exécute du code
- 🟠 identifiants de la base métier dans une connexion Airflow chiffrée, plus en variables d'environnement
- 🟢 image API multi-étapes : ni compilateurs ni données dans l'image finale
- 🟢 UID paramétrable (`ARG UID`) pour les dossiers montés sous Linux ; limites CPU / mémoire par conteneur
"""
        )

theme.speaker_notes("next")
