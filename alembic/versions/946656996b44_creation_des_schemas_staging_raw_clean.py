"""creation des schemas staging raw clean

Revision ID: 946656996b44
Revises:
Create Date: 2026-09-09 00:07:59.252183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '946656996b44'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crée les trois schémas du pipeline."""
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS clean")


def downgrade() -> None:
    """Supprime les trois schémas et tout leur contenu."""
    op.execute("DROP SCHEMA IF EXISTS clean CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE")
