"""add material table (Task 15)

Revision ID: d7f3a8b2e9c5
Revises: b5e8f1a2c3d4
Create Date: 2026-09-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f3a8b2e9c5"
down_revision: str | None = "b5e8f1a2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("enterprise_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.String(length=20), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("indexed", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("material", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_enterprise_id"), ["enterprise_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_material_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_material_category"), ["category"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("material", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_category"))
        batch_op.drop_index(batch_op.f("ix_material_project_id"))
        batch_op.drop_index(batch_op.f("ix_material_enterprise_id"))

    op.drop_table("material")
