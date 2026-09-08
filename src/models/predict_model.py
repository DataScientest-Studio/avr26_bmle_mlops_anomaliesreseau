"""Prédiction & scoring d'anomalie à partir de l'artefact entraîné.

Charge le modèle, prédit la consommation attendue ``ŷ`` à partir des features
temporelles, puis marque une anomalie quand le résidu standardisé dépasse le
seuil : ``score = |y − ŷ − médiane| / σ̂robuste`` , ``anomalie = score > k``.

Périmètre modèle : on lit le CSV et on écrit le résultat scoré dans un fichier
(``data/processed/``). Le branchement base viendra plus tard.
"""

from __future__ import annotations

import argparse
import logging

import joblib
import numpy as np
import polars as pl

from src.config.config import settings
from src.models.train_model import MODEL_PATH

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("predict")


def load_artifact(path=None) -> dict:
    """Charge l'artefact de modèle (dict model + métadonnées de seuil)."""
    return joblib.load(path or MODEL_PATH)


def score(feats: pl.DataFrame, artifact: dict | None = None) -> pl.DataFrame:
    """Scoring d'anomalie sur une table de features déjà construite.

    Renvoie ``date_heure, y_true, y_pred, residual, anomaly_score, is_anomaly,
    model_version``.
    """
    artifact = artifact or load_artifact()

    cols = artifact["feature_cols"]
    target = artifact["target"]

    data = feats.drop_nulls(subset=cols).sort("date_heure")
    X = data.select(cols).to_numpy()
    y_pred = artifact["model"].predict(X)

    has_target = target in data.columns and data.get_column(target).null_count() < len(data)

    if has_target:
        y_true = data.get_column(target).to_numpy().astype(float)
        residual = y_true - y_pred
        scale = artifact["resid_scale"] or 1e-9
        ascore = np.abs(residual - artifact["resid_median"]) / scale
        is_anom = ascore > artifact["k"]

        return data.select("date_heure").with_columns(
            pl.Series("y_true", y_true),
            pl.Series("y_pred", y_pred),
            pl.Series("residual", residual),
            pl.Series("anomaly_score", ascore),
            pl.Series("is_anomaly", is_anom),
            pl.lit(artifact["version"]).alias("model_version"),
        )
    else:
        return data.select("date_heure").with_columns(
            pl.Series("y_pred", y_pred),
            pl.lit(artifact["version"]).alias("model_version"),
        )   


def score_from_csv(artifact: dict | None = None) -> pl.DataFrame:
    """Lit le CSV national, construit les features et score toute la série."""
    from src.models.data_source import load_features_from_csv

    return score(load_features_from_csv(), artifact)


def predict_to_file(artifact: dict | None = None) -> int:
    """Score depuis le CSV et écrit le résultat dans ``data/processed/``."""
    settings.ensure_dirs()
    result = score_from_csv(artifact)
    out = settings.data_dir / "processed" / "predictions.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.write_parquet(out)
    n_anom = int(result.get_column("is_anomaly").sum())
    logger.info("%d lignes scorées, %d anomalies → %s", result.height, n_anom, out)
    return result.height


def main() -> None:
    parser = argparse.ArgumentParser(description="Prédiction / scoring d'anomalie")
    parser.add_argument(
        "--save", action="store_true",
        help="écrire les prédictions dans data/processed/predictions.parquet",
    )
    args = parser.parse_args()
    if args.save:
        predict_to_file()
    else:
        result = score_from_csv()
        n_anom = int(result.get_column("is_anomaly").sum())
        logger.info("%d lignes scorées, %d anomalies", result.height, n_anom)
        print(result.tail(10))


if __name__ == "__main__":
    main()
