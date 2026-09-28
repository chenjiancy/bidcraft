"""add llm_call_log.cached_tokens (Task 10, BP-10)

Revision ID: b5e8f1a2c3d4
Revises: a3b7c9d2e1f4
Create Date: 2026-09-29 03:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e8f1a2c3d4"
down_revision: str | None = "a3b7c9d2e1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_call_log", sa.Column("cached_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_call_log", "cached_tokens")
