"""Mission thread tracking for checkpoint retention.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the mission_threads table."""
    op.create_table(
        "mission_threads",
        sa.Column("thread_id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mission_threads_created_at", "mission_threads", ["created_at"])


def downgrade() -> None:
    """Drop the mission_threads table."""
    op.drop_index("ix_mission_threads_created_at", table_name="mission_threads")
    op.drop_table("mission_threads")
