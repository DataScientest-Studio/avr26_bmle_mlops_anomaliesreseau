def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS clean")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS clean CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE")
