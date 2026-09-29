"""add template table (Task 17)

Revision ID: e8d2f4a1b7c3
Revises: a3c9f1e5d8b2
Create Date: 2026-09-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8d2f4a1b7c3"
down_revision: str | None = "a3c9f1e5d8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enterprise_id", sa.String(length=32), nullable=False),
        sa.Column("agency", sa.String(length=200), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("referenced", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprise.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("template", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_template_enterprise_id"), ["enterprise_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_template_agency"), ["agency"], unique=False)
        batch_op.create_index(batch_op.f("ix_template_doc_type"), ["doc_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("template", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_template_doc_type"))
        batch_op.drop_index(batch_op.f("ix_template_agency"))
        batch_op.drop_index(batch_op.f("ix_template_enterprise_id"))

    op.drop_table("template")
