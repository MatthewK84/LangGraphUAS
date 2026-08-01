"""SQLAlchemy ORM models.

Uses the typed 2.0 ``Mapped`` style so column types are visible to mypy
(Principle 8).
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class AircraftRow(Base):
    """Persistent aircraft reference record."""

    __tablename__ = "aircraft"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    max_payload_kg: Mapped[float] = mapped_column(Float, nullable=False)
    battery_wh: Mapped[float] = mapped_column(Float, nullable=False)
    max_wind_mps: Mapped[float] = mapped_column(Float, nullable=False)
    cruise_speed_mps: Mapped[float] = mapped_column(Float, nullable=False)
    hover_power_w: Mapped[float] = mapped_column(Float, nullable=False)
    cruise_power_w: Mapped[float] = mapped_column(Float, nullable=False)
    max_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    min_temp_c: Mapped[float] = mapped_column(Float, nullable=False, server_default="-20.0")


class PayloadRow(Base):
    """Persistent payload reference record."""

    __tablename__ = "payloads"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    power_draw_w: Mapped[float] = mapped_column(Float, nullable=False)


class MissionThreadRow(Base):
    """Creation time of a planning thread, used to age out checkpoints.

    LangGraph's checkpoint tables carry no timestamp we can portably query, so
    the application records when each thread was first planned. Retention reads
    this table to decide what to delete via the checkpointer's own API rather
    than reaching into its internal schema.
    """

    __tablename__ = "mission_threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
