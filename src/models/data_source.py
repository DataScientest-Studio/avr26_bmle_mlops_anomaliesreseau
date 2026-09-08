"""Source de données du modèle : le CSV national éCO2mix (pas de base).

Remplace la lecture en base (``store.read_series``) par une lecture du CSV
téléchargé depuis ODRE. Le parsing des en-têtes est **tolérant** : on normalise
les noms de colonnes (minuscules, sans accents) puis on mappe vers le schéma
canonique, pour absorber les variantes de nommage du fichier RTE.

Le jour où la base existe, il suffira de rebrancher ``read_series`` à la place
de ``load_features_from_csv`` dans ``train_model`` / ``predict_model``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import polars as pl

from src.config.config import settings

# Schéma canonique attendu en aval (cible + exogènes utiles).
CANONICAL_COLUMNS: tuple[str, ...] = (
    "date_heure", "consommation", "prevision_j1", "prevision_j",
    "fioul", "charbon", "gaz", "nucleaire", "eolien", "solaire",
    "hydraulique", "pompage", "bioenergies", "ech_physiques", "taux_co2",
)
NUMERIC_COLUMNS: tuple[str, ...] = tuple(c for c in CANONICAL_COLUMNS if c != "date_heure")

# En-tête normalisé (RTE) -> nom canonique.
_HEADER_MAP: dict[str, str] = {
    "date_heure": "date_heure",
    "date_et_heure": "date_heure",  # libellé réel du fichier national
    "consommation": "consommation",
    "prevision_j_1": "prevision_j1",
    "prevision_j1": "prevision_j1",
    "prevision_j": "prevision_j",
    "fioul": "fioul",
    "charbon": "charbon",
    "gaz": "gaz",
    "nucleaire": "nucleaire",
    "eolien": "eolien",
    "solaire": "solaire",
    "hydraulique": "hydraulique",
    "pompage": "pompage",
    "bioenergies": "bioenergies",
    "ech_physiques": "ech_physiques",
    "taux_de_co2": "taux_co2",
    "taux_co2": "taux_co2",
}


def _norm(name: str) -> str:
    """minuscule, sans accents ni unité entre parenthèses, séparateurs -> underscore.

    Ex. ``"Consommation (MW)"`` -> ``"consommation"`` ;
        ``"Date et Heure"`` -> ``"date_et_heure"`` ;
        ``"Taux de CO2 (g/kWh)"`` -> ``"taux_de_co2"``.
    """
    s = re.sub(r"\(.*?\)", "", name)  # retire l'unité entre parenthèses
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s


def load_raw_csv(path: str | Path | None = None, separator: str = ";") -> pl.DataFrame:
    """Lit le CSV éCO2mix et le ramène au schéma canonique (types corrigés).

    * séparateur ``;`` par défaut (format ODRE) ;
    * en-têtes mappés de façon tolérante ;
    * ``date_heure`` en datetime conscient du fuseau (Europe/Paris) ;
    * colonnes de puissance en ``Float64`` (virgule décimale gérée).
    """
    path = Path(path or settings.raw_csv_path)
    # Tout en Utf8 d'abord : on maîtrise le typage nous-mêmes.
    df = pl.read_csv(
        path, separator=separator, infer_schema_length=0, encoding="utf8-lossy"
    )
    rename = {c: _HEADER_MAP[_norm(c)] for c in df.columns if _norm(c) in _HEADER_MAP}
    df = df.rename(rename)
    keep = [c for c in CANONICAL_COLUMNS if c in df.columns]
    df = df.select(keep)

    exprs: list[pl.Expr] = []
    if "date_heure" in df.columns:
        exprs.append(
            pl.col("date_heure")
            .str.to_datetime(strict=False, time_zone="UTC")
            .dt.convert_time_zone(settings.timezone)
            .alias("date_heure")
        )
    for c in NUMERIC_COLUMNS:
        if c in df.columns:
            exprs.append(
                pl.col(c).str.replace_all(",", ".").cast(pl.Float64, strict=False).alias(c)
            )
    df = df.with_columns(exprs)
    # Le réalisé national définitif est publié au pas de 30 min : une ligne sur
    # deux (les :15 et :45) a une consommation vide. On retire ces lignes
    # structurellement vides pour ne pas fabriquer 50 % de la cible par
    # interpolation ; la grille régulière (30 min) est alors sans trou.
    if "consommation" in df.columns:
        df = df.filter(pl.col("consommation").is_not_null())
    return df.sort("date_heure")


def load_features_from_csv(path: str | Path | None = None) -> pl.DataFrame:
    """CSV -> nettoyage -> table de features (entrée directe du modèle)."""
    # Imports locaux pour éviter les cycles et garder ce module léger.
    from src.features.build_features import build_features
    from src.features.preprocess import clean_series

    raw = load_raw_csv(path)
    return build_features(clean_series(raw))
