"""merge_recycle_bin_and_generated_doc_heads

Revision ID: 3b426c0f86f8
Revises: a1b2c3d4e5f6, c1a2b3d4e5f6
Create Date: 2026-09-30 00:10:28.194387

"""

from collections.abc import Sequence

revision: str = "3b426c0f86f8"
down_revision: tuple[str, str] | None = ("a1b2c3d4e5f6", "c1a2b3d4e5f6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
