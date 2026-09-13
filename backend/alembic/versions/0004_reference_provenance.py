"""Record where every reference figure came from.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Existing rows predate provenance. They get an empty object rather than a
# fabricated source: the operational gate treats an unaccounted-for number as a
# blocker, which is the correct reading of a row nobody has vouched for.
_EMPTY: str = "'{}'"


def upgrade() -> None:
    """Add a provenance object to both reference tables."""
    for table in ("aircraft", "payloads"):
        op.add_column(
            table,
            sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text(_EMPTY)),
        )


def downgrade() -> None:
    """Drop provenance from both reference tables."""
    for table in ("aircraft", "payloads"):
        op.drop_column(table, "provenance")
