"""Charge un CSV eCO2mix dans une table de staging via COPY."""
import sys
from pathlib import Path

import psycopg

from src.config.settings import settings
from src.data.chemins import RAW, creer_dossiers

DEFAUT = RAW / "eco2mix-national-cons-def.csv"
TABLE = "staging.eco2mix_national_cons_def"


def charger(csv: Path, table: str = TABLE) -> int:
    """Vide la table de staging puis y charge le CSV. Renvoie le nombre de lignes."""
    creer_dossiers()
    if not csv.exists():
        raise FileNotFoundError(csv)

    sql = (
        f"COPY {table} FROM STDIN "
        "WITH (FORMAT csv, HEADER true, DELIMITER ';', ENCODING 'UTF8')"
    )
    with psycopg.connect(settings.dsn) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {table}")
        with cur.copy(sql) as cp, open(csv, "rb") as f:
            while chunk := f.read(1 << 20):
                cp.write(chunk)
        conn.commit()
        return cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


if __name__ == "__main__":
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAUT
    print(f"{charger(chemin):,} lignes chargées dans {TABLE}".replace(",", " "))
