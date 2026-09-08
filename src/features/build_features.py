"""Feature engineering — assemble la table analytique servant au modèle.

Le contrat de sortie (colonnes stables) est le point de couplage unique avec
l'aval : ``training.py``, ``predict.py`` et la surcouche RAG ne connaissent que
cette table. On combine quatre familles de features :

  1. calendrier déterministe (``calendar_fr``) ;
  2. encodage harmonique des saisonnalités (termes de Fourier) — l'équivalent
     d'une base de Fourier pour représenter des cycles lisses sans one-hot ;
  3. mémoire de la série : lags saisonniers (J-1, J-7) et statistiques
     glissantes (moyenne/écart-type sur jour et semaine) ;
  4. baselines B1/B2 (``baselines``).
"""

from __future__ import annotations

import math

import polars as pl

from src.features.baselines import STEPS_PER_DAY, STEPS_PER_WEEK, add_baselines
from src.features.calendar_fr import add_calendar_features

# Nombre d'harmoniques retenues par saisonnalité (la PHASE est calendaire, pas
# un index physique — voir add_fourier_terms). 3 pour le journalier (double
# bosse matin/soir), 2 pour l'hebdo et l'annuel.
FOURIER_HARMONICS: dict[str, int] = {"day": 3, "week": 2, "year": 2}
# Lags saisonniers utiles à la prévision de la cible.
SEASONAL_LAGS: dict[str, int] = {"lag_1d": STEPS_PER_DAY, "lag_7d": STEPS_PER_WEEK}


def add_fourier_terms(lf: pl.LazyFrame, ts_col: str = "date_heure") -> pl.LazyFrame:
    """Encode les cycles via des paires (sin, cos) de **phase calendaire**.

    Les phases sont normalisées dans [0, 1) et calées sur le calendrier *local*,
    pas sur un index physique :

    * journalier : ``quarter_of_day / steps_per_day`` ;
    * hebdomadaire : ``(dow·steps_per_day + quarter_of_day) / (7·steps_per_day)`` ;
    * annuel : ``(doy − 1) / 365.25``.

    Deux propriétés cruciales, absentes de l'ancienne version à index physique :
    la phase reste **verrouillée sur l'horloge locale** à travers les changements
    d'heure, et l'encodage est **indépendant de la cadence** (15 ou 30 min).
    Nécessite les colonnes calendaires (``add_calendar_features`` en amont).
    """
    spd = STEPS_PER_DAY
    phases: dict[str, pl.Expr] = {
        "day": pl.col("quarter_of_day") / spd,
        "week": (pl.col("dow") * spd + pl.col("quarter_of_day")) / (7 * spd),
        "year": (pl.col("doy") - 1) / 365.25,
    }
    exprs: list[pl.Expr] = []
    for name, n_harm in FOURIER_HARMONICS.items():
        for k in range(1, n_harm + 1):
            ang = 2.0 * math.pi * k * phases[name]
            exprs.append(ang.sin().alias(f"fourier_{name}_sin{k}"))
            exprs.append(ang.cos().alias(f"fourier_{name}_cos{k}"))
    return lf.with_columns(exprs)


def add_lag_and_rolling(
    lf: pl.LazyFrame, target_col: str = "consommation"
) -> pl.LazyFrame:
    """Ajoute lags saisonniers et statistiques glissantes de la cible.

    Attention fuite temporelle : les rolling utilisent une fenêtre *passée*
    décalée d'un pas (``shift(1)``) pour ne jamais inclure l'instant courant.
    """
    exprs: list[pl.Expr] = [
        pl.col(target_col).shift(lag).alias(f"{target_col}_{name}")
        for name, lag in SEASONAL_LAGS.items()
    ]
    shifted = pl.col(target_col).shift(1)
    exprs += [
        shifted.rolling_mean(STEPS_PER_DAY).alias(f"{target_col}_roll_mean_1d"),
        shifted.rolling_std(STEPS_PER_DAY).alias(f"{target_col}_roll_std_1d"),
        shifted.rolling_mean(STEPS_PER_WEEK).alias(f"{target_col}_roll_mean_1w"),
        shifted.rolling_std(STEPS_PER_WEEK).alias(f"{target_col}_roll_std_1w"),
    ]
    return lf.with_columns(exprs)


def build_features(
    source: pl.LazyFrame | pl.DataFrame,
    ts_col: str = "date_heure",
    target_col: str = "consommation",
    zone: str | None = None,
) -> pl.DataFrame:
    """Chaîne complète de feature engineering ; renvoie la table analytique.

    Entrée attendue : série nettoyée par ``preprocess.clean_series`` (grille
    15 min régulière, drapeaux ``is_missing`` / ``is_imputed``).
    """
    lf = source.lazy() if isinstance(source, pl.DataFrame) else source
    lf = add_calendar_features(lf, ts_col=ts_col, zone=zone)
    lf = add_fourier_terms(lf, ts_col=ts_col)
    lf = add_lag_and_rolling(lf, target_col=target_col)
    lf = add_baselines(lf, ts_col=ts_col, target_col=target_col)
    return lf.sort(ts_col).collect()
