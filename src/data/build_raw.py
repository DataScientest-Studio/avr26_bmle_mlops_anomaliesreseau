"""Typage et chargement de staging vers raw."""
from pathlib import Path

import psycopg

from src.config.settings import settings

SQL = Path(__file__).parent / "sql"


def executer(fichier: str) -> int:
    with psycopg.connect(settings.dsn) as conn, conn.cursor() as cur:
        cur.execute((SQL / fichier).read_text())
        inserees = cur.rowcount
        conn.commit()
    return inserees


if __name__ == "__main__":
    n = executer("staging_to_raw_national.sql")
    print(f"{n} lignes insérées dans raw.eco2mix_national")
