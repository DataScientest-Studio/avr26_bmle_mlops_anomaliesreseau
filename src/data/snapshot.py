"""Extrait un instantané figé d'une table vers data/processed.

Le parquet produit est immuable : c'est lui qui alimente l'entraînement,
jamais la base, qui elle continue d'évoluer au fil des révisions RTE.

Usage :
    python -m src.data.snapshot
    python -m src.data.snapshot raw.eco2mix_national
    python -m src.data.snapshot raw.eco2mix_national 2013-01-01 2026-01-01
"""
import sys
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, text

from src.config.settings import settings
from src.data.chemins import PROCESSED, creer_dossiers

TABLE = "clean.eco2mix_national"


def _construire_requete(table: str, debut: str | None, fin: str | None) -> tuple[str, dict]:
    """Assemble la requête et ses paramètres selon la période demandée."""
    conditions, params = [], {}
    if debut:
        conditions.append("date_heure >= :debut")
        params["debut"] = debut
    if fin:
        conditions.append("date_heure < :fin")
        params["fin"] = fin

    requete = f"SELECT * FROM {table}"
    if conditions:
        requete += " WHERE " + " AND ".join(conditions)
    return requete + " ORDER BY date_heure", params


def _nommer(table: str, debut: str | None, fin: str | None) -> str:
    """Nom de fichier : table, période couverte, date d'extraction."""
    morceaux = [table.split(".")[-1]]
    if debut or fin:
        morceaux.append(f"{debut or 'debut'}_{fin or 'fin'}")
    morceaux.append(f"{date.today():%Y%m%d}")
    return "_".join(morceaux) + ".parquet"


def _ecrire_fiche(chemin, df: pd.DataFrame, table: str, requete: str) -> None:
    """Fiche d'accompagnement : sans elle, un parquet daté n'est pas traçable."""
    lignes = [
        f"# Snapshot {chemin.name}",
        "",
        f"- Extrait le : {date.today():%Y-%m-%d}",
        f"- Source : {table}",
        f"- Lignes : {len(df):,}".replace(",", " "),
        f"- Colonnes : {len(df.columns)}",
    ]
    if "date_heure" in df.columns and len(df):
        lignes.append(f"- Période : {df['date_heure'].min()} → {df['date_heure'].max()}")
    if "nature" in df.columns:
        lignes.append("- Répartition par nature :")
        lignes += [
            f"  - {n} : {c:,}".replace(",", " ")
            for n, c in df["nature"].value_counts().items()
        ]
    lignes += ["", "## Requête", "", "```sql", requete, "```"]
    chemin.with_suffix(".md").write_text("\n".join(lignes) + "\n")


def extraire(table: str = TABLE, debut: str | None = None, fin: str | None = None):
    """Extrait la table vers un parquet daté. Renvoie (chemin, nombre de lignes)."""
    creer_dossiers()
    requete, params = _construire_requete(table, debut, fin)

    moteur = create_engine(settings.sqlalchemy_url)
    with moteur.connect() as conn:
        df = pd.read_sql(text(requete), conn, params=params)

    chemin = PROCESSED / _nommer(table, debut, fin)
    df.to_parquet(chemin, index=False)
    _ecrire_fiche(chemin, df, table, requete)
    return chemin, len(df)


if __name__ == "__main__":
    args = sys.argv[1:]
    table = args[0] if args else TABLE
    debut = args[1] if len(args) > 1 else None
    fin = args[2] if len(args) > 2 else None

    chemin, n = extraire(table, debut, fin)
    print(f"{n:,} lignes → {chemin}".replace(",", " "))
