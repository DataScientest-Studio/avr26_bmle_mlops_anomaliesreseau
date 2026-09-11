"""Nettoyage et régularisation de la série (polars, lazy autant que possible).

Objectif : livrer une série au pas de 15 min strictement régulier, sans
doublon ni trou implicite, avec un drapeau explicite sur tout point imputé —
condition d'une décomposition saisonnière (MSTL) propre en aval.

Sur les changements d'heure : ``date_heure`` étant conscient du fuseau, la
grille régulière construite en tz-aware saute automatiquement l'heure
disparue au printemps et matérialise l'heure doublée en automne. On ne
manipule jamais l'heure locale « nue ».
"""

from __future__ import annotations

import polars as pl

from src.config.config import settings

# Longueur maximale d'un trou comblé par interpolation = 1 heure de points.
# (4 points à 15 min, 2 points à 30 min). Au-delà, on laisse un trou explicite.
MAX_INTERP_GAP = max(1, 60 // settings.freq_minutes)


def _dedupe_and_sort(lf: pl.LazyFrame, ts_col: str) -> pl.LazyFrame:
    """Trie et supprime les horodatages dupliqués (on garde le dernier reçu)."""
    return lf.sort(ts_col).unique(subset=ts_col, keep="last", maintain_order=True)


def _regular_grid(df: pl.DataFrame, ts_col: str, tz: str) -> pl.DataFrame:
    """Construit la grille 15 min complète et y aligne les observations."""
    if df.is_empty():
        return df
    lo = df.get_column(ts_col).min()
    hi = df.get_column(ts_col).max()
    grid = pl.datetime_range(
        lo, hi, interval=settings.freq, time_zone=tz, eager=True
    ).alias(ts_col).to_frame()
    return grid.join(df, on=ts_col, how="left")


def clean_series(
    source: pl.LazyFrame | pl.DataFrame,
    ts_col: str = "date_heure",
    target_col: str = "consommation",
    tz: str | None = None,
) -> pl.DataFrame:
    """Pipeline de nettoyage complet ; renvoie un ``DataFrame`` régularisé.

    Étapes :
      1. tri + déduplication des horodatages ;
      2. valeurs physiquement impossibles → null (consommation <= 0) ;
      3. grille 15 min régulière (gère les changements d'heure) ;
      4. drapeau ``is_missing`` sur la cible avant imputation ;
      5. interpolation linéaire des trous courts (<= 1 h), trous longs laissés
         explicites ;
      6. drapeau ``is_imputed`` = comblé par interpolation.
    """
    tz = tz or settings.timezone
    lf = source.lazy() if isinstance(source, pl.DataFrame) else source
    # Normalise le fuseau : la base renvoie du TIMESTAMPTZ en UTC, la source
    # synthétique en Europe/Paris. On aligne tout sur le fuseau cible avant la
    # grille (sinon les clés de jointure ont des types de fuseau différents).
    dtype = lf.collect_schema().get(ts_col)
    if isinstance(dtype, pl.Datetime) and dtype.time_zone is not None:
        lf = lf.with_columns(pl.col(ts_col).dt.convert_time_zone(tz).alias(ts_col))
    lf = _dedupe_and_sort(lf, ts_col)

    # Valeurs aberrantes de la cible → null (la conso nationale est > 0).
    lf = lf.with_columns(
        pl.when(pl.col(target_col) <= 0)
        .then(None)
        .otherwise(pl.col(target_col))
        .alias(target_col)
    )

    df = lf.collect()
    df = _regular_grid(df, ts_col, tz)

    # Marque les trous de la cible avant toute imputation.
    df = df.with_columns(pl.col(target_col).is_null().alias("is_missing"))

    # Interpolation limitée aux trous courts : on interpole tout, puis on
    # ré-annule les points appartenant à un trou plus long que MAX_INTERP_GAP.
    gap_id = (~pl.col("is_missing")).cum_sum()
    df = df.with_columns(gap_id.alias("_seg"))
    long_gap = (
        pl.col("is_missing")
        & (pl.col("is_missing").sum().over("_seg") > MAX_INTERP_GAP)
    )
    df = df.with_columns(
        pl.col(target_col).interpolate().alias("_interp"),
        long_gap.alias("_long_gap"),
    ).with_columns(
        pl.when(pl.col("_long_gap"))
        .then(None)
        .otherwise(pl.col("_interp"))
        .alias(target_col),
        (pl.col("is_missing") & ~pl.col("_long_gap")).alias("is_imputed"),
    )

    return df.drop("_seg", "_interp", "_long_gap")
