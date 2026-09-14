"""Record the battery pack's documented takeoff minimum, where one exists.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add aircraft.pack_min_takeoff_c.

    Nullable with no default. Most airframes have no such procedure on record,
    and inventing one would either ground them or, worse, imply a limit was
    checked when nothing was.
    """
    op.add_column("aircraft", sa.Column("pack_min_takeoff_c", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop aircraft.pack_min_takeoff_c."""
    op.drop_column("aircraft", "pack_min_takeoff_c")
