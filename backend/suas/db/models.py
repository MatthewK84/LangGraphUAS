"""SQLAlchemy ORM models.

Uses the typed 2.0 ``Mapped`` style so column types are visible to mypy
(Principle 8).
"""

from sqlalchemy import Float, String
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


class PayloadRow(Base):
    """Persistent payload reference record."""

    __tablename__ = "payloads"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    power_draw_w: Mapped[float] = mapped_column(Float, nullable=False)
