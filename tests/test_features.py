"""Tests du feature engineering et des baselines."""

from __future__ import annotations

import polars as pl

from src.features.baselines import STEPS_PER_WEEK, robust_zscore
from src.features.build_features import build_features
from src.features.preprocess import clean_series


def test_build_features_contract(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    feats = build_features(clean)
    expected = {
        "date_heure", "consommation", "dow", "quarter_of_day", "is_holiday",
        "is_weekend", "fourier_day_sin1", "fourier_week_cos1",
        "consommation_lag_7d", "consommation_roll_mean_1d", "resid_b1", "resid_b2",
    }
    assert expected <= set(feats.columns)
    # Fourier borné dans [-1, 1].
    assert feats.get_column("fourier_day_sin1").abs().max() <= 1.0 + 1e-9


def test_baseline_b1_removes_seasonality(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    feats = build_features(clean)
    resid = feats.get_column("resid_b1").drop_nulls()
    conso = feats.get_column("consommation")
    # Le résidu B1 (lag 7 j) a une amplitude bien plus faible que le signal brut.
    assert resid.std() < conso.std()
    # Les premiers points (< 1 semaine) n'ont pas de lag ⇒ null.
    assert feats.get_column("resid_b1").head(STEPS_PER_WEEK).null_count() == STEPS_PER_WEEK


def test_robust_zscore_flags_spike(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    feats = build_features(clean)
    # Injecte un pic artificiel sur resid_b1 et vérifie que le z-score le capte.
    lf = feats.lazy().with_columns(
        pl.when(pl.int_range(pl.len()) == pl.len() - 1)
        .then(pl.col("resid_b1") + 50_000.0)
        .otherwise(pl.col("resid_b1"))
        .alias("resid_b1")
    )
    z = robust_zscore(lf, "resid_b1").collect().get_column("z_resid_b1")
    assert z.abs().max() > 5.0


def test_no_temporal_leakage_in_rolling(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    feats = build_features(clean)
    # roll_mean_1d au 1er point valide utilise du passé décalé (shift(1)) ⇒ null au début.
    assert feats.get_column("consommation_roll_mean_1d").head(1).null_count() == 1
