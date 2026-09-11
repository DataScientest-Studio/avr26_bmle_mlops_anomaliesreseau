"""fonction de conversion texte vers entier

Revision ID: 0004_fonction_vers_int
Revises: 0003_raw_national
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_fonction_vers_int"
down_revision: Union[str, Sequence[str], None] = "0003_raw_national"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convertit un champ texte du staging en entier.

    'ND' (non disponible) et la chaîne vide deviennent NULL.
    """
    op.execute("""
        CREATE OR REPLACE FUNCTION staging.vers_int(v text) RETURNS integer
            LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
        $$ SELECT nullif(nullif(btrim(v), 'ND'), '')::integer $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS staging.vers_int(text)")
