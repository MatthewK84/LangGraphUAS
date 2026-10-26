"""Add rate_limit_buckets, the request budget every worker shares (#84).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create rate_limit_buckets."""
    op.create_table(
        "rate_limit_buckets",
        sa.Column("bucket", sa.String(length=64), primary_key=True),
        sa.Column("hits", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    """Drop rate_limit_buckets."""
    op.drop_table("rate_limit_buckets")
