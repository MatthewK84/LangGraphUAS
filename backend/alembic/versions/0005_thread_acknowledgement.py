"""Record who acknowledged a mission assessment, and which one.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All nullable: threads planned before this migration were never acknowledged,
# and backfilling a signature nobody gave would be the worst possible default.
_COLUMNS: tuple[sa.Column[object], ...] = (
    sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("ack_actor", sa.String(), nullable=True),
    sa.Column("ack_action", sa.String(), nullable=True),
    sa.Column("ack_inputs_hash", sa.String(), nullable=True),
    sa.Column("ack_calculator_version", sa.String(), nullable=True),
)


def upgrade() -> None:
    """Add acknowledgement columns to mission_threads."""
    for column in _COLUMNS:
        op.add_column("mission_threads", column)


def downgrade() -> None:
    """Drop the acknowledgement columns."""
    for column in _COLUMNS:
        op.drop_column("mission_threads", column.name)
