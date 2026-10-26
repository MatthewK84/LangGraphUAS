"""Add api_key_last_seen, the client IP a retired key is bound to.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create api_key_last_seen."""
    op.create_table(
        "api_key_last_seen",
        sa.Column("key_hash", sa.String(length=64), primary_key=True),
        sa.Column("client_ip", sa.String(length=45), nullable=False),
    )


def downgrade() -> None:
    """Drop api_key_last_seen."""
    op.drop_table("api_key_last_seen")
