"""table de staging du jeu national consolide/definitif

Revision ID: 0002_staging_national
Revises: 946656996b44
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_staging_national"
down_revision: Union[str, Sequence[str], None] = "946656996b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLONNES = [
    "perimetre", "nature", "date", "heure", "date_heure",
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
    cols = ",\n    ".join(f"{c} text" for c in COLONNES)
    op.execute(f"CREATE TABLE staging.eco2mix_national_cons_def (\n    {cols}\n)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staging.eco2mix_national_cons_def")
