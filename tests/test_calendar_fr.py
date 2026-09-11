"""Tests du calendrier : fériés, week-end, cycles, DST."""

from __future__ import annotations

import polars as pl

from src.config.config import settings
from src.features.calendar_fr import add_calendar_features


def _series(days: int = 20) -> pl.LazyFrame:
    ts = pl.datetime_range(
        pl.datetime(2026, 7, 1), pl.datetime(2026, 7, 1) + pl.duration(days=days),
        interval=settings.freq, time_zone="Europe/Paris", eager=True,
    )
    return pl.DataFrame({"date_heure": ts, "consommation": [1.0] * len(ts)}).lazy()


def test_bastille_day_is_holiday() -> None:
    out = add_calendar_features(_series()).collect()
    ferie = out.filter(pl.col("date_heure").dt.date() == pl.date(2026, 7, 14))
    assert ferie.get_column("is_holiday").all()
    # Le 15 juillet (mercredi) n'est pas férié.
    non = out.filter(pl.col("date_heure").dt.date() == pl.date(2026, 7, 15))
    assert not non.get_column("is_holiday").any()


def test_cyclic_columns_ranges() -> None:
    out = add_calendar_features(_series()).collect()
    assert out.get_column("quarter_of_day").max() == settings.steps_per_day - 1
    assert out.get_column("quarter_of_day").min() == 0
    assert set(out.get_column("dow").unique().to_list()) <= set(range(7))


def test_dst_flag_summer() -> None:
    out = add_calendar_features(_series(days=1)).collect()
    # Juillet = heure d'été en France (offset +02:00).
    assert out.get_column("is_dst").all()


def test_weekend_flag() -> None:
    out = add_calendar_features(_series()).collect()
    sat = out.filter(pl.col("date_heure").dt.date() == pl.date(2026, 7, 4))  # samedi
    assert sat.get_column("is_weekend").all()
