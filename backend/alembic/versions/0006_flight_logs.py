"""Store uploaded flight logs and the power estimates derived from them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the flight log and sample tables."""
    op.create_table(
        "flight_logs",
        sa.Column("log_id", sa.String(), primary_key=True),
        sa.Column("airframe_id", sa.String(), nullable=False, index=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False, unique=True),
        sa.Column("raw_csv", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.Column("hover_median_w", sa.Float(), nullable=True),
        sa.Column("hover_samples", sa.Integer(), nullable=True),
        sa.Column("hover_confidence", sa.String(), nullable=True),
        sa.Column("cruise_median_w", sa.Float(), nullable=True),
        sa.Column("cruise_samples", sa.Integer(), nullable=True),
        sa.Column("cruise_confidence", sa.String(), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "flight_log_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "log_id",
            sa.String(),
            sa.ForeignKey("flight_logs.log_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alt_m", sa.Float(), nullable=False),
        sa.Column("power_w", sa.Float(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("phase", sa.String(), nullable=False),
    )


def downgrade() -> None:
    """Drop the flight log tables."""
    op.drop_table("flight_log_samples")
    op.drop_table("flight_logs")
