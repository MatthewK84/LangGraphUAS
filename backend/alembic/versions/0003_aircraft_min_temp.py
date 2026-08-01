"""Add a lower operating temperature limit to aircraft.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add aircraft.min_temp_c with a conservative default for existing rows."""
    op.add_column(
        "aircraft",
        sa.Column("min_temp_c", sa.Float(), nullable=False, server_default="-20.0"),
    )


def downgrade() -> None:
    """Drop aircraft.min_temp_c."""
    op.drop_column("aircraft", "min_temp_c")
