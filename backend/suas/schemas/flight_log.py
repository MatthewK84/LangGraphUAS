"""Recorded flight telemetry.

A flight log is the only input this system accepts as evidence of what an
airframe actually draws. Everything else in the reference data is a published
figure, a derivation, or an estimate, and the operational gate treats it
accordingly.

Parsing is strict on purpose. A log is an uploaded file, which makes its column
names and any free-text field an untrusted input surface: only the columns below
are read, every one of them is numeric or an enum, and anything else in the file
is ignored rather than carried forward.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FlightPhase(StrEnum):
    """What the aircraft was doing when a sample was taken."""

    HOVER = "hover"
    CLIMB = "climb"
    CRUISE = "cruise"
    DESCENT = "descent"
    UNKNOWN = "unknown"


class FlightLogSample(BaseModel):
    """One row of recorded telemetry.

    ``power_w`` is the figure the estimator uses. When a log records volts and
    amps instead, it is derived here rather than at the point of use, so there is
    exactly one definition of what "power" means for a log.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    alt_m: float
    power_w: float | None = Field(default=None, ge=0.0)
    voltage_v: float | None = Field(default=None, ge=0.0)
    current_a: float | None = Field(default=None, ge=0.0)
    tas_mps: float | None = Field(default=None, ge=0.0)
    groundspeed_mps: float | None = Field(default=None, ge=0.0)
    wind_mps: float | None = Field(default=None, ge=0.0)
    outside_temp_c: float | None = None
    payload_id: str | None = None
    phase: FlightPhase = FlightPhase.UNKNOWN

    @model_validator(mode="after")
    def _require_a_power_figure(self) -> "FlightLogSample":
        """Reject a row that carries neither power nor the means to compute it."""
        if self.power_w is None and (self.voltage_v is None or self.current_a is None):
            raise ValueError("row has neither power_w nor both voltage_v and current_a")
        return self

    @property
    def effective_power_w(self) -> float:
        """Return recorded power, or volts times amps when power was not logged."""
        if self.power_w is not None:
            return self.power_w
        # The validator guarantees both are present when power_w is not.
        assert self.voltage_v is not None and self.current_a is not None
        return self.voltage_v * self.current_a

    @property
    def speed_mps(self) -> float | None:
        """Return airspeed if logged, otherwise ground speed."""
        return self.tas_mps if self.tas_mps is not None else self.groundspeed_mps
