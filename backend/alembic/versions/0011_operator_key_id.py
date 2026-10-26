"""Record which operator's API key planned each mission.

Existing missions were planned under the single shared key, so they are
backfilled to that key's operator id, 'default'. A deployment that keeps
SUAS_API_KEY keeps reading its threads, open interrupts included.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add mission_threads.operator_key_id and backfill existing rows to 'default'."""
    op.add_column("mission_threads", sa.Column("operator_key_id", sa.String(), nullable=True))
    op.create_index("ix_mission_threads_operator_key_id", "mission_threads", ["operator_key_id"])
    op.execute("UPDATE mission_threads SET operator_key_id = 'default'")


def downgrade() -> None:
    """Drop mission_threads.operator_key_id."""
    op.drop_index("ix_mission_threads_operator_key_id", table_name="mission_threads")
    op.drop_column("mission_threads", "operator_key_id")
