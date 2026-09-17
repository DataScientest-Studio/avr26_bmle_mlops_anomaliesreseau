"""Intégration MLflow — suivi d'expériences + versioning de modèle.

Deux fonctions publiques :

* ``log_training_run(artifact, extra_params)`` : ouvre un *run*, logue
  params/métriques, enregistre le modèle sklearn au **Model Registry** et le
  seuil de détection en artefact JSON, puis pose l'alias **champion** si le
  nouveau modèle est meilleur (MAE de validation plus basse) que l'actuel.
* ``load_champion_artifact()`` : recharge, côté prédiction, le modèle taggé
  champion depuis le registry et reconstruit l'artefact complet.

**Non bloquant par conception** : si aucun serveur MLflow n'est configuré ou
joignable, ``log_training_run`` renvoie ``None`` et l'entraînement continue
(l'artefact ``model.joblib`` local reste la source de repli).
"""

from __future__ import annotations

import logging
import os

from src.config.config import settings

logger = logging.getLogger("mlflow")

# Clés de l'artefact nécessaires au scoring (tout sauf l'objet modèle lui-même).
_THRESHOLD_KEYS = (
    "feature_cols", "target", "resid_median", "resid_scale", "k", "version", "kind",
)


def tracking_uri() -> str:
    """URI de suivi effective : MLFLOW_TRACKING_URI standard sinon config projet."""
    return os.environ.get("MLFLOW_TRACKING_URI") or settings.mlflow_tracking_uri


def mlflow_enabled() -> bool:
    """MLflow est actif dès qu'une URI de suivi est fournie."""
    return bool(tracking_uri())


def _setup():
    import mlflow

    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_experiment(settings.mlflow_experiment)
    return mlflow


def log_training_run(artifact: dict, extra_params: dict | None = None) -> str | None:
    """Logue l'entraînement dans MLflow et gère la promotion champion.

    Renvoie l'``run_id`` créé, ou ``None`` si MLflow est désactivé/indisponible.
    """
    if not mlflow_enabled():
        return None
    try:
        import mlflow

        mlflow = _setup()
        meta = artifact["metadata"]
        with mlflow.start_run(run_name=artifact["version"]) as run:
            mlflow.log_params(
                {
                    "kind": artifact["kind"],
                    "k": artifact["k"],
                    "n_features": meta["n_features"],
                    "freq": settings.freq,
                    "source": settings.source,
                    **(extra_params or {}),
                }
            )
            mlflow.log_metrics(
                {
                    "mae_valid": meta["mae_valid"],
                    "resid_scale": artifact["resid_scale"],
                    "n_train": float(meta["n_train"]),
                    "n_valid": float(meta["n_valid"]),
                }
            )
            mlflow.set_tags(
                {"date_min": meta["date_min"], "date_max": meta["date_max"]}
            )
            # Seuil + liste de features en artefact JSON (indispensable au scoring).
            mlflow.log_dict({k: artifact[k] for k in _THRESHOLD_KEYS}, "threshold.json")
            # Modèle sklearn → Model Registry (une nouvelle version à chaque run).
            # pip_requirements explicites : on court-circuite l'inférence
            # d'environnement de MLflow (déterministe et sans conflit uv/lock).
            info = mlflow.sklearn.log_model(
                artifact["model"], name="model",
                registered_model_name=settings.mlflow_model_name,
                pip_requirements=["scikit-learn", "numpy", "cloudpickle"],
                # cloudpickle plutôt que skops : skops rejette le TreePredictor
                # de HistGradientBoosting (« type non fiable »).
                serialization_format="cloudpickle",
            )
            run_id = run.info.run_id

        version = getattr(info, "registered_model_version", None)
        _promote_if_better(settings.mlflow_model_name, version, meta["mae_valid"], run_id)
        logger.info("Run MLflow loggé (%s), version modèle %s", run_id, version)
        return run_id
    except Exception as exc:  # pragma: no cover - dépend d'un serveur réel
        logger.warning("MLflow indisponible — on garde le joblib local (%s)", exc)
        return None


def _promote_if_better(name: str, version, mae: float, run_id: str) -> None:
    """Pose l'alias champion sur la nouvelle version si sa MAE est la plus basse."""
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    if version is None:
        versions = client.search_model_versions(f"name = '{name}'")
        version = max((int(v.version) for v in versions), default=None)
    if version is None:
        return
    # Trace la métrique sur la version pour une comparaison directe.
    client.set_model_version_tag(name, str(version), "mae_valid", f"{mae:.6f}")
    alias = settings.mlflow_champion_alias

    try:
        champ = client.get_model_version_by_alias(name, alias)
    except Exception:
        champ = None

    if champ is None:
        client.set_registered_model_alias(name, alias, str(version))
        logger.info("Alias '%s' posé sur la version %s (premier modèle)", alias, version)
        return

    champ_mae = float(champ.tags.get("mae_valid", "inf"))
    if mae < champ_mae:
        client.set_registered_model_alias(name, alias, str(version))
        logger.info(
            "Nouveau champion v%s (MAE %.1f < %.1f)", version, mae, champ_mae
        )
    else:
        logger.info(
            "Version %s conservée hors champion (MAE %.1f ≥ %.1f)",
            version, mae, champ_mae,
        )


def load_champion_artifact() -> dict:
    """Recharge le modèle champion depuis le registry et reconstruit l'artefact.

    Lève une exception si MLflow est indisponible ou sans champion — l'appelant
    (``predict_model``) bascule alors sur le joblib local.
    """
    import json

    import mlflow

    mlflow = _setup()
    from mlflow.tracking import MlflowClient

    name, alias = settings.mlflow_model_name, settings.mlflow_champion_alias
    client = MlflowClient()
    mv = client.get_model_version_by_alias(name, alias)
    model = mlflow.sklearn.load_model(f"models:/{name}@{alias}")
    path = client.download_artifacts(mv.run_id, "threshold.json")
    with open(path) as f:
        threshold = json.load(f)
    artifact = {"model": model, **threshold}
    artifact.setdefault("metadata", {"mlflow_version": mv.version})
    logger.info("Modèle champion chargé depuis MLflow (version %s)", mv.version)
    return artifact
