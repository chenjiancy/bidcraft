"""add project.parse_status (Task 8)

Revision ID: f7a2c91b4d8e
Revises: 3e186ccdf00c
Create Date: 2026-09-28 20:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a2c91b4d8e"
down_revision: str | None = "3e186ccdf00c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "parse_status",
                sa.String(length=32),
                nullable=False,
                server_default="INIT",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("parse_status")
