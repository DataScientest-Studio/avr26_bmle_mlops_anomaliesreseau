"""Tests du modèle : entraînement, artefact, scoring, détection d'un pic."""

from __future__ import annotations

import polars as pl

from src.features.build_features import build_features
from src.features.preprocess import clean_series
from src.models.predict_model import score
from src.models.train_model import select_feature_columns, train


def _feats(synthetic_raw: pl.DataFrame) -> pl.DataFrame:
    return build_features(clean_series(synthetic_raw))


def test_train_produces_artifact(synthetic_raw: pl.DataFrame) -> None:
    feats = _feats(synthetic_raw)
    art = train(feats=feats, kind="linear")
    assert art["feature_cols"], "aucune feature sélectionnée"
    assert art["resid_scale"] > 0
    # La cible et les colonnes fuyantes ne sont jamais des features.
    for leak in ("consommation", "prevision_j1", "resid_b1", "nucleaire"):
        assert leak not in art["feature_cols"]


def test_score_contract_and_columns(synthetic_raw: pl.DataFrame) -> None:
    feats = _feats(synthetic_raw)
    art = train(feats=feats, kind="hgb")
    out = score(feats, art)
    assert {
        "date_heure", "y_true", "y_pred", "residual",
        "anomaly_score", "is_anomaly", "model_version",
    } <= set(out.columns)
    assert out.get_column("anomaly_score").min() >= 0


def test_injected_spike_is_flagged(synthetic_raw: pl.DataFrame) -> None:
    feats = _feats(synthetic_raw)
    art = train(feats=feats, kind="hgb")
    # Injecte un pic massif sur le dernier point et vérifie qu'il est marqué.
    spiked = feats.with_columns(
        pl.when(pl.int_range(pl.len()) == pl.len() - 1)
        .then(pl.col("consommation") + 30_000.0)
        .otherwise(pl.col("consommation"))
        .alias("consommation")
    )
    out = score(spiked, art)
    assert bool(out.tail(1).get_column("is_anomaly")[0]) is True
