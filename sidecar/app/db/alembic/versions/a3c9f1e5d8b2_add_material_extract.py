"""add material_extract_item

Revision ID: a3c9f1e5d8b2
Revises: d7f3a8b2e9c5
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "a3c9f1e5d8b2"
down_revision = "d7f3a8b2e9c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_extract_item",
        sa.Column("id", sa.String(length=32), nullable=False, primary_key=True),
        sa.Column("enterprise_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requirement_name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="score_table"),
        sa.Column("source_anchor", sa.Text(), nullable=True),
        sa.Column("selected_material_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    with op.batch_alter_table("material_extract_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mei_enterprise_id"), ["enterprise_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_mei_project_id"), ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_table("material_extract_item")
