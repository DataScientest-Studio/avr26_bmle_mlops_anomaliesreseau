"""Tests du nettoyage : déduplication, grille régulière, imputation."""

from __future__ import annotations

import polars as pl

from src.config.config import settings
from src.features.preprocess import clean_series


def test_regular_grid_no_duplicates(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    ts = clean.get_column("date_heure")
    # Aucun doublon d'horodatage.
    assert ts.n_unique() == clean.height
    # Grille strictement régulière au pas configuré.
    diffs = ts.diff().drop_nulls().dt.total_minutes().unique().to_list()
    assert diffs == [settings.freq_minutes]


def test_gap_flagged_and_short_gap_imputed(synthetic_raw: pl.DataFrame) -> None:
    clean = clean_series(synthetic_raw)
    # Le trou de 2 points (≤ 1 h) est marqué manquant puis imputé.
    assert clean.get_column("is_missing").sum() == 2
    assert clean.get_column("is_imputed").sum() == 2
    # Après imputation courte, plus de null sur la cible.
    assert clean.get_column("consommation").null_count() == 0


def test_negative_values_removed() -> None:
    tz = "Europe/Paris"
    ts = pl.datetime_range(
        pl.datetime(2026, 1, 6), pl.datetime(2026, 1, 6, 4, 0),
        interval=settings.freq, time_zone=tz, eager=True,
    )
    df = pl.DataFrame({"date_heure": ts, "consommation": [-5.0] + [100.0] * (len(ts) - 1)})
    clean = clean_series(df)
    # La valeur négative devient un trou (imputé car isolé).
    assert clean.get_column("is_missing").sum() == 1
