"""Live telemetry from an aircraft already flying.

A snapshot is what the aircraft reports about itself mid-mission. It is not a
plan and it is not trusted the way a briefed assessment is: whoever holds the API
key can post one, its string fields are enum-validated so they cannot carry
prose, and its age is checked before it is allowed to carry operational weight.

``remaining_leg_m`` is required rather than inferred from the briefed distance.
An aircraft that has deviated, held, or been retasked no longer has the route it
was briefed on, and assuming otherwise would compute a residual for a mission
nobody is flying.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from suas.schemas.flight_log import FlightPhase


class TelemetrySource(StrEnum):
    """Where a snapshot came from."""

    ONBOARD = "onboard"
    GCS = "gcs"
    SIMULATED = "simulated"


class TelemetrySnapshot(BaseModel):
    """One point-in-time report from an aircraft in flight."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str = Field(min_length=1, max_length=255)
    ts: datetime
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    alt_m: float

    # State of charge as a fraction, because percent invites a factor-of-100 bug
    # at exactly the moment it matters least to be wrong.
    soc_fraction: float = Field(ge=0.0, le=1.0)

    # What is actually left to fly. Required: see the module docstring.
    remaining_leg_m: float = Field(ge=0.0)
    remaining_hover_s: float = Field(default=0.0, ge=0.0)

    oat_c: float
    voltage_v: float | None = Field(default=None, ge=0.0)
    current_a: float | None = Field(default=None, ge=0.0)
    power_w: float | None = Field(default=None, ge=0.0)
    wind_mps: float | None = Field(default=None, ge=0.0)
    wind_from_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    payload_attached: bool = True
    phase: FlightPhase = FlightPhase.UNKNOWN
    source: TelemetrySource = TelemetrySource.ONBOARD

    def age_s(self, now: datetime) -> float:
        """Return how old this snapshot is, in seconds, never negative.

        A clock-skewed snapshot from the future is treated as fresh rather than
        as negatively aged, so skew cannot manufacture freshness it does not have
        in the other direction either.
        """
        return max(0.0, (now - self.ts).total_seconds())
