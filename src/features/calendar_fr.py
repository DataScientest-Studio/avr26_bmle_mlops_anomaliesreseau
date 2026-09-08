"""Calendrier français — le contexte déterministe de la consommation.

La consommation électrique est pilotée par le calendrier bien plus que par le
hasard : un jour férié ressemble à un dimanche, une vague de vacances creuse la
demande. Encoder ces effets *avant* la détection évite au modèle de crier à
l'anomalie sur chaque pont de mai.

Aucune dépendance réseau : ``holidays`` et ``vacances-scolaires-france``
embarquent leurs règles.
"""

from __future__ import annotations

import datetime as dt
import functools

import holidays
import polars as pl

from src.config.config import settings


@functools.lru_cache(maxsize=8)
def _fr_holidays(year_lo: int, year_hi: int) -> holidays.HolidayBase:
    return holidays.France(years=range(year_lo, year_hi + 1))


@functools.lru_cache(maxsize=1)
def _school_calendar():  # pragma: no cover - dépend de la lib externe
    try:
        from vacances_scolaires_france import SchoolHolidayDates

        return SchoolHolidayDates()
    except Exception:
        return None


def _is_school_holiday(day: dt.date, zone: str) -> bool:
    cal = _school_calendar()
    if cal is None:
        return False
    try:
        return bool(cal.is_holiday_for_zone(day, zone))
    except Exception:
        return False


def add_calendar_features(
    lf: pl.LazyFrame,
    ts_col: str = "date_heure",
    zone: str | None = None,
) -> pl.LazyFrame:
    """Ajoute les colonnes calendaires déterministes à la série.

    Colonnes produites :

    * cycles : ``year, month, day, dow (0=lundi), hour, minute, doy,
      quarter_of_day`` (0..95, l'index du pas de 15 min dans la journée) ;
    * drapeaux : ``is_weekend, is_holiday, is_school_holiday, is_bridge_day``
      (jour ouvré isolé entre férié/week-end, très marqué en France) ;
    * ``is_dst`` : True à l'heure d'été (offset +02:00), utile pour tracer les
      transitions de changement d'heure.
    """
    zone = zone or settings.school_zone

    # Bornes d'années présentes → construction du set de fériés (mappé via Python).
    lf = lf.with_columns(
        pl.col(ts_col).dt.year().alias("year"),
        pl.col(ts_col).dt.month().alias("month"),
        pl.col(ts_col).dt.day().alias("day"),
        pl.col(ts_col).dt.weekday().alias("dow_1"),  # 1=lundi … 7=dimanche
        pl.col(ts_col).dt.hour().alias("hour"),
        pl.col(ts_col).dt.minute().alias("minute"),
        pl.col(ts_col).dt.ordinal_day().alias("doy"),
        # Composante DST non nulle ⇒ heure d'été (base_utc_offset = offset standard).
        (pl.col(ts_col).dt.dst_offset().dt.total_seconds() > 0).alias("is_dst"),
    ).with_columns(
        (pl.col("dow_1") - 1).alias("dow"),  # 0=lundi pour cohérence code
        # Index du pas dans la journée (0..steps_per_day-1), conscient de la
        # cadence : 0..95 à 15 min, 0..47 à 30 min. Cast Int32 obligatoire :
        # hour (Int8) * 60 déborderait le range Int8 (max 127).
        (
            (pl.col("hour").cast(pl.Int32) * 60 + pl.col("minute").cast(pl.Int32))
            // settings.freq_minutes
        ).alias("quarter_of_day"),
        (pl.col("dow_1") >= 6).alias("is_weekend"),
    )

    # Fériés + vacances scolaires : évalués en Python sur les dates distinctes,
    # puis joints (bien plus efficace que map_elements ligne à ligne).
    dates = (
        lf.select(pl.col(ts_col).dt.date().alias("d"))
        .unique()
        .collect()
        .get_column("d")
        .to_list()
    )
    if dates:
        y_lo, y_hi = min(dates).year, max(dates).year
        fr = _fr_holidays(y_lo, y_hi)
        cal = pl.DataFrame(
            {
                "d": dates,
                "is_holiday": [d in fr for d in dates],
                "is_school_holiday": [_is_school_holiday(d, zone) for d in dates],
            }
        ).lazy()
    else:
        cal = pl.DataFrame(
            schema={"d": pl.Date, "is_holiday": pl.Boolean, "is_school_holiday": pl.Boolean}
        ).lazy()

    lf = lf.with_columns(pl.col(ts_col).dt.date().alias("_d")).join(
        cal, left_on="_d", right_on="d", how="left"
    )

    # Jour de pont : jour ouvré non férié, coincé entre un férié/week-end de part
    # et d'autre (veille et lendemain non ouvrés au niveau journalier).
    day_flags = (
        lf.select("_d", "is_weekend", "is_holiday")
        .unique(subset="_d")
        .sort("_d")
        .with_columns(
            (pl.col("is_weekend") | pl.col("is_holiday")).alias("off"),
        )
        .with_columns(
            (
                ~pl.col("off")
                & pl.col("off").shift(1).fill_null(False)  # noqa: E501
                & pl.col("off").shift(-1).fill_null(False)
            ).alias("is_bridge_day")
        )
        .select("_d", "is_bridge_day")
    )

    lf = (
        lf.join(day_flags, on="_d", how="left")
        .with_columns(
            pl.col("is_holiday").fill_null(False),
            pl.col("is_school_holiday").fill_null(False),
            pl.col("is_bridge_day").fill_null(False),
        )
        .drop("_d", "dow_1")
    )
    return lf
