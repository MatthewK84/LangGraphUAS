"""Add weather_cache, the weather readings every worker shares (#85).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create weather_cache."""
    op.create_table(
        "weather_cache",
        sa.Column("cell", sa.String(length=32), primary_key=True),
        sa.Column("reading", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    """Drop weather_cache."""
    op.drop_table("weather_cache")
