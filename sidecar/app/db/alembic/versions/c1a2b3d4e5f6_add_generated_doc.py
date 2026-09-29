"""add generated_doc table (Task 19)

Revision ID: c1a2b3d4e5f6
Revises: f9e3d5a7b2c1
Create Date: 2026-09-29 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "f9e3d5a7b2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_doc",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enterprise_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("chapter", sa.String(length=255), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "source_template_version", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_msg", sa.Text(), nullable=True, default=None),
        sa.Column(
            "rendered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            default=None,
        ),
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
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprise.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("generated_doc", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_generated_doc_enterprise_id"), ["enterprise_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_generated_doc_project_id"), ["project_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("generated_doc", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_generated_doc_project_id"))
        batch_op.drop_index(batch_op.f("ix_generated_doc_enterprise_id"))

    op.drop_table("generated_doc")
