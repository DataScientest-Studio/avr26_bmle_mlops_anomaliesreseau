"""Chemins du projet, créés à la demande."""
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
DATA = RACINE / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"


def creer_dossiers() -> None:
    for d in (RAW, INTERIM, PROCESSED, EXTERNAL):
        d.mkdir(parents=True, exist_ok=True)
