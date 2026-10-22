"""Create the users table (baseline, same as the old schema.sql).

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS only here, so databases created by the old schema.sql are
    # adopted as-is. Later migrations state exact changes and never use it.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            email        TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
            created_at   TIMESTAMPTZ NOT NULL,
            updated_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS users_created_at_idx ON users (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE users")
