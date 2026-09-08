"""Baselines de détection — les deux détecteurs « gratuits » exigés par le sujet.

Elles servent de référence de performance ET de filet de sécurité en
production : un système qui retombe sur B1/B2 quand le modèle principal dérive
reste exploitable.
"""

from __future__ import annotations

import polars as pl

from src.config.config import settings

# Nombre de pas par jour/semaine, dérivé de la cadence (96/672 à 15 min ;
# 48/336 à 30 min — le réalisé national définitif est à 30 min).
STEPS_PER_DAY = settings.steps_per_day
STEPS_PER_WEEK = STEPS_PER_DAY * 7


def add_baselines(
    lf: pl.LazyFrame,
    ts_col: str = "date_heure",
    target_col: str = "consommation",
) -> pl.LazyFrame:
    """Ajoute les résidus des deux baselines.

    * **B1 — persistance saisonnière** : écart à la même heure, même jour de la
      semaine précédente (lag de 672 pas). Capture l'essentiel de la
      saisonnalité journalière + hebdomadaire sans aucun modèle.
    * **B2 — écart à la prévision RTE** : la prévision J-1 est publiée dans la
      donnée ; ``consommation - prevision_j1`` est une baseline forte fournie.

    On expose les écarts bruts (``resid_b1``, ``resid_b2``). Le seuillage
    (z-score robuste / seuil dynamique) est appliqué en aval par le modèle.
    """
    exprs: list[pl.Expr] = [
        (pl.col(target_col) - pl.col(target_col).shift(STEPS_PER_WEEK)).alias("resid_b1"),
    ]
    # B2 seulement si la prévision est disponible dans le schéma.
    schema_names = lf.collect_schema().names()
    if "prevision_j1" in schema_names:
        exprs.append(
            (pl.col(target_col) - pl.col("prevision_j1")).alias("resid_b2")
        )
    return lf.with_columns(exprs)


def robust_zscore(
    lf: pl.LazyFrame,
    resid_col: str,
    window: int = STEPS_PER_WEEK,
    out_col: str | None = None,
) -> pl.LazyFrame:
    """Z-score robuste glissant d'un résidu : (r - médiane) / (1.4826·MAD).

    Base du seuillage : |z| > k (k≈3.5) marque un point anormal. Robuste aux
    régimes non stationnaires (vague de froid) grâce à la fenêtre glissante et
    à la MAD (insensible aux valeurs extrêmes).
    """
    out_col = out_col or f"z_{resid_col}"
    med = pl.col(resid_col).rolling_median(window_size=window, min_samples=window // 4)
    mad = (
        (pl.col(resid_col) - med)
        .abs()
        .rolling_median(window_size=window, min_samples=window // 4)
    )
    return lf.with_columns(
        ((pl.col(resid_col) - med) / (1.4826 * mad + 1e-9)).alias(out_col)
    )
