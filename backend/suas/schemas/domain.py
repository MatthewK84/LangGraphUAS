"""Immutable domain models.

These describe the physical characteristics of aircraft and payloads. They are
frozen so that a value, once loaded, cannot be mutated in place (Principle 2).

Each carries a ``provenance`` map keyed by field name. It is optional on the
model but not in practice: a row loaded without it is a row whose numbers nobody
has accounted for, and the operational gate reads it that way.
"""

from pydantic import BaseModel, ConfigDict, Field

from suas.schemas.provenance import FieldProvenance


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
    min_temp_c: float = Field(default=-20.0)
    # A procedure limit on the battery pack, where the manufacturer documents
    # one. Distinct from min_temp_c, which is what the airframe tolerates:
    # an aircraft rated to -20 C can still have a pack that must not launch
    # below +10 C. None means no such procedure is on record.
    pack_min_takeoff_c: float | None = Field(default=None)
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)


class Payload(BaseModel):
    """Physical and power characteristics of a sensor payload."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    weight_kg: float = Field(ge=0.0)
    power_draw_w: float = Field(ge=0.0)
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
