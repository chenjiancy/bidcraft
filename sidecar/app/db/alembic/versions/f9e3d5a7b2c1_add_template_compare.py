"""add template_compare table (Task 18)

Revision ID: f9e3d5a7b2c1
Revises: e8d2f4a1b7c3
Create Date: 2026-09-29 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9e3d5a7b2c1"
down_revision: str | None = "e8d2f4a1b7c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_compare",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enterprise_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("matched_template_id", sa.String(length=32), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("similarity_score", sa.Integer(), nullable=True),
        sa.Column("work_dir", sa.Text(), nullable=False),
        sa.Column("association_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("findings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="matched"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "ready_at",
            sa.DateTime(timezone=True),
            nullable=True,
            default=None,
        ),
        sa.Column("bp4_summary_json", sa.Text(), nullable=False, server_default="{}"),
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
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_template_id"], ["template.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("template_compare", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_template_compare_enterprise_id"), ["enterprise_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_template_compare_project_id"), ["project_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("template_compare", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_template_compare_project_id"))
        batch_op.drop_index(batch_op.f("ix_template_compare_enterprise_id"))

    op.drop_table("template_compare")
