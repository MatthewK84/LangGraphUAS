"""Initial schema: aircraft and payload reference tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the aircraft and payloads tables."""
    op.create_table(
        "aircraft",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("max_payload_kg", sa.Float(), nullable=False),
        sa.Column("battery_wh", sa.Float(), nullable=False),
        sa.Column("max_wind_mps", sa.Float(), nullable=False),
        sa.Column("cruise_speed_mps", sa.Float(), nullable=False),
        sa.Column("hover_power_w", sa.Float(), nullable=False),
        sa.Column("cruise_power_w", sa.Float(), nullable=False),
        sa.Column("max_temp_c", sa.Float(), nullable=False),
    )
    op.create_index("ix_aircraft_id", "aircraft", ["id"])
    op.create_table(
        "payloads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("power_draw_w", sa.Float(), nullable=False),
    )
    op.create_index("ix_payloads_id", "payloads", ["id"])


def downgrade() -> None:
    """Drop the aircraft and payloads tables."""
    op.drop_index("ix_payloads_id", table_name="payloads")
    op.drop_table("payloads")
    op.drop_index("ix_aircraft_id", table_name="aircraft")
    op.drop_table("aircraft")
