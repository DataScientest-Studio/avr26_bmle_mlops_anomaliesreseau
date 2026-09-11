"""Entraînement du modèle d'anomalie — approche recommandée par le mentor.

Principe : **on ne traite pas la série comme une Time Series**. On prédit la
consommation à partir de **features temporelles** (calendrier + Fourier + lags)
avec un régresseur supervisé simple, puis l'anomalie est le **résidu**
standardisé de façon robuste : ``|y − ŷ|`` normalisé par la MAD des résidus.

Le modèle n'a pas vocation à être performant (exigence mentor : « même une
régression linéaire basique »), mais à produire un **artefact** versionnable
inséré dans l'architecture MLOps.

Usage :
    uv run python -m src.models.train_model                 # lit la base, entraîne
    uv run python -m src.models.train_model --model linear  # régression linéaire
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

import joblib
import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

from src.config.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("train")

TARGET = "consommation"
MODEL_PATH = settings.models_dir / "model.joblib"

# Colonnes à exclure des features : cible, exogènes qui « donnent la réponse »
# (prévision RTE = B2), résidus baselines, drapeaux qualité, et les filières de
# production contemporaines (on veut un résidu inexpliqué par le CALENDRIER seul).
_EXCLUDE = {
    TARGET, "date_heure", "prevision_j1", "prevision_j",
    "resid_b1", "resid_b2", "is_missing", "is_imputed",
    "fioul", "charbon", "gaz", "nucleaire", "eolien", "solaire",
    "hydraulique", "pompage", "bioenergies", "ech_physiques", "taux_co2",
}


def select_feature_columns(df: pl.DataFrame) -> list[str]:
    """Colonnes numériques utilisées comme features (déterministe, ordonné)."""
    cols = []
    for c in df.columns:
        if c in _EXCLUDE:
            continue
        if df.schema[c].is_numeric() or df.schema[c] == pl.Boolean:
            cols.append(c)
    return cols


def _make_model(kind: str):
    if kind == "linear":
        return LinearRegression()
    return HistGradientBoostingRegressor(
        max_depth=6, learning_rate=0.08, max_iter=300, l2_regularization=1.0,
        random_state=0,
    )


def load_feature_frame() -> pl.DataFrame:
    """Charge la table de features depuis le CSV national (périmètre modèle).

    Le jour où la base existe, remplacer par ``store.read_series`` — la suite
    du code est identique (elle ne dépend que du DataFrame de features).
    """
    from src.models.data_source import load_features_from_csv

    return load_features_from_csv()


def train(
    feats: pl.DataFrame | None = None,
    kind: str = "hgb",
    valid_frac: float = 0.2,
    k: float = 3.5,
) -> dict:
    """Entraîne le régresseur, calibre le seuil robuste, sauvegarde l'artefact."""
    settings.ensure_dirs()
    feats = feats if feats is not None else load_feature_frame()

    feature_cols = select_feature_columns(feats)

    # On ne garde que les lignes complètes (features + cible), le début de série
    # ayant des lags nuls.
    needed = feature_cols + [TARGET]
    data = feats.drop_nulls(subset=needed).sort("date_heure")
    if data.height < 100:
        raise ValueError(f"Trop peu de lignes exploitables : {data.height}")

    X = data.select(feature_cols).to_numpy()
    y = data.get_column(TARGET).to_numpy()

    # Découpe temporelle (pas de shuffle : on respecte la causalité).
    n_valid = max(1, int(data.height * valid_frac))
    X_tr, y_tr = X[:-n_valid], y[:-n_valid]
    X_va, y_va = X[-n_valid:], y[-n_valid:]

    model = _make_model(kind)
    model.fit(X_tr, y_tr)

    # Résidus de validation (jamais vus) pour une calibration honnête du seuil.
    resid_va = y_va - model.predict(X_va)
    resid_median = float(np.median(resid_va))
    resid_mad = float(np.median(np.abs(resid_va - resid_median)))
    mae = float(mean_absolute_error(y_va, model.predict(X_va)))

    version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifact = {
        "model": model,
        "kind": kind,
        "feature_cols": feature_cols,
        "target": TARGET,
        "resid_median": resid_median,
        "resid_scale": 1.4826 * resid_mad,  # ≈ σ robuste
        "k": k,
        "version": version,
        "metadata": {
            "trained_at": version,
            "n_train": int(len(y_tr)),
            "n_valid": int(len(y_va)),
            "mae_valid": mae,
            "n_features": len(feature_cols),
            "date_min": str(data.get_column("date_heure").min()),
            "date_max": str(data.get_column("date_heure").max()),
        },
    }
    joblib.dump(artifact, MODEL_PATH)
    logger.info(
        "Modèle '%s' entraîné — MAE(valid)=%.1f MW, %d features, seuil robuste σ̂=%.1f",
        kind, mae, len(feature_cols), artifact["resid_scale"],
    )
    logger.info("Artefact sauvegardé : %s (version %s)", MODEL_PATH, version)
    (settings.logs_dir / f"train_{version}.json").write_text(
        json.dumps(artifact["metadata"], indent=2)
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Entraînement modèle d'anomalie")
    parser.add_argument(
        "--model", dest="kind", choices=["hgb", "linear"], default="hgb",
        help="hgb = gradient boosting (défaut), linear = régression linéaire",
    )
    args = parser.parse_args()
    train(kind=args.kind)


if __name__ == "__main__":
    main()
