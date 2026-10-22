"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    # Plain SQL via op.execute(...). Expand, then contract: the old and new
    # app versions must both work while this migration is applied.
    raise NotImplementedError("write the upgrade SQL")


def downgrade() -> None:
    raise NotImplementedError("write the downgrade SQL")
