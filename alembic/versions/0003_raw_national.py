"""table raw du jeu national (consolide + definitif)

Revision ID: 0003_raw_national
Revises: 0002_staging_national
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_raw_national"
down_revision: Union[str, Sequence[str], None] = "0002_staging_national"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESURES = [
    "consommation", "prevision_j1", "prevision_j",
    "fioul", "charbon", "gaz", "nucleaire", "eolien", "solaire",
    "hydraulique", "pompage", "bioenergies", "ech_physiques", "taux_co2",
    "ech_comm_angleterre", "ech_comm_espagne", "ech_comm_italie",
    "ech_comm_suisse", "ech_comm_allemagne_belgique",
    "fioul_tac", "fioul_cogen", "fioul_autres",
    "gaz_tac", "gaz_cogen", "gaz_ccg", "gaz_autres",
    "hydraulique_fil_eau_eclusee", "hydraulique_lacs",
    "hydraulique_step_turbinage",
    "bioenergies_dechets", "bioenergies_biomasse", "bioenergies_biogaz",
]


def upgrade() -> None:
    cols = ",\n    ".join(f"{c} integer" for c in MESURES)
    op.execute(f"""
        CREATE TABLE raw.eco2mix_national (
            date_heure  timestamptz NOT NULL,
            nature      text        NOT NULL,
            perimetre   text,
            {cols},
            ingested_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (date_heure, nature)
        )
    """)
    op.execute("""
        CREATE INDEX idx_raw_national_date_heure
        ON raw.eco2mix_national (date_heure)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw.eco2mix_national")
