"""Immutable domain models.

These describe the physical characteristics of aircraft and payloads. They are
frozen so that a value, once loaded, cannot be mutated in place (Principle 2).
"""

from pydantic import BaseModel, ConfigDict, Field


class Aircraft(BaseModel):
    """Physical and performance characteristics of an sUAS airframe."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    weight_kg: float = Field(gt=0.0)
    max_payload_kg: float = Field(ge=0.0)
    battery_wh: float = Field(gt=0.0)
    max_wind_mps: float = Field(ge=0.0)
    cruise_speed_mps: float = Field(gt=0.0)
    hover_power_w: float = Field(gt=0.0)
    cruise_power_w: float = Field(gt=0.0)
    max_temp_c: float


class Payload(BaseModel):
    """Physical and power characteristics of a sensor payload."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    weight_kg: float = Field(ge=0.0)
    power_draw_w: float = Field(ge=0.0)
