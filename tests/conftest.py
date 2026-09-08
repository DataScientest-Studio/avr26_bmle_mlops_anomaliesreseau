"""Fixtures partagées : génère une série éCO2mix synthétique (aucun réseau).

La cadence suit ``settings.freq`` (30 min par défaut, 15 min si ANOM_FREQ=15m),
pour que les tests restent cohérents avec la configuration du pipeline.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from src.config.config import settings

SPD = settings.steps_per_day        # pas par jour (48 à 30 min, 96 à 15 min)
SPW = SPD * 7                        # pas par semaine


@pytest.fixture
def synthetic_raw() -> pl.DataFrame:
    """Série ~3 semaines à la cadence configurée, tz Europe/Paris, saisonnière.

    Contient volontairement un doublon d'horodatage et un petit trou (points
    retirés) pour exercer le nettoyage.
    """
    tz = "Europe/Paris"
    ts = pl.datetime_range(
        pl.datetime(2026, 1, 5, 0, 0),  # un lundi
        pl.datetime(2026, 1, 5, 0, 0) + pl.duration(days=21),
        interval=settings.freq,
        time_zone=tz,
        eager=True,
        closed="left",
    )
    n = len(ts)
    conso = []
    for i in range(n):
        daily = 6000.0 * math.sin(2 * math.pi * (i % SPD) / SPD - math.pi / 2)
        weekly = 2000.0 * math.sin(2 * math.pi * (i % SPW) / SPW)
        conso.append(50000.0 + daily + weekly + 200.0 * math.sin(i))
    df = pl.DataFrame(
        {
            "date_heure": ts,
            "consommation": conso,
            "prevision_j1": [c + 300.0 for c in conso],
            "nucleaire": [40000.0] * n,
        }
    )
    # Doublon (dernière ligne rejouée) + trou court (2 points ≤ MAX_INTERP_GAP).
    dup = df.tail(1)
    df = pl.concat([df, dup])
    df = df.with_row_index("_i").filter(~pl.col("_i").is_in([100, 101])).drop("_i")
    return df
