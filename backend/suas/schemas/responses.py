"""Response and computed-result models.

These are the explicit shapes returned to the client and produced by the pure
calculation layer (Principle 8).
"""

from pydantic import BaseModel


class WeatherReading(BaseModel):
    """A point-in-time meteorological reading."""

    temperature_c: float
    wind_speed_mps: float
    wind_direction: float
    humidity_percent: float
    conditions: str


class SafetyFlags(BaseModel):
    """Boolean pass/fail flags for each independent safety constraint."""

    battery_viable: bool
    payload_within_limits: bool
    wind_within_limits: bool
    temperature_within_limits: bool


class BatteryCheck(BaseModel):
    """Energy budget analysis for the planned mission."""

    energy_required_wh: float
    usable_capacity_wh: float
    margin_wh: float
    reserve_percent: float
    is_viable: bool


class Calculations(BaseModel):
    """Full deterministic assessment of a mission."""

    density_altitude_m: float
    energy_required_wh: float
    payload_margin_kg: float
    battery_check: BatteryCheck
    safety_flags: SafetyFlags


class PlanResponse(BaseModel):
    """The complete result of a mission planning run."""

    is_viable: bool
    calculations: Calculations | None
    weather: WeatherReading | None
    report: str
    thread_id: str


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str
    service: str
    version: str
