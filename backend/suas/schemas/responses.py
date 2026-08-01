"""Response and computed-result models.

These are the explicit shapes returned to the client and produced by the pure
calculation layer (Principle 8).
"""

from enum import Enum

from pydantic import BaseModel, Field


class WeatherSource(str, Enum):
    """Provenance of a weather reading."""

    LIVE = "live"
    FALLBACK = "fallback"


class WeatherReading(BaseModel):
    """A point-in-time meteorological reading."""

    temperature_c: float
    wind_speed_mps: float
    wind_gust_mps: float = 0.0
    wind_direction: float
    humidity_percent: float
    conditions: str
    source: WeatherSource = WeatherSource.LIVE

    @property
    def is_live(self) -> bool:
        """Return whether the reading came from the live provider."""
        return self.source is WeatherSource.LIVE


class SafetyFlags(BaseModel):
    """Boolean pass/fail flags for each independent safety constraint."""

    battery_viable: bool
    payload_within_limits: bool
    wind_within_limits: bool
    gust_within_limits: bool
    temperature_within_limits: bool
    cruise_achievable: bool


class BatteryCheck(BaseModel):
    """Energy budget analysis for the planned mission."""

    energy_required_wh: float
    usable_capacity_wh: float
    margin_wh: float
    reserve_percent: float
    temperature_factor: float = 1.0
    is_viable: bool


class EnergyBreakdown(BaseModel):
    """Energy demanded by each phase of the planned profile, in watt-hours."""

    climb_wh: float
    cruise_wh: float
    hover_wh: float
    descent_wh: float
    total_wh: float


class Calculations(BaseModel):
    """Full deterministic assessment of a mission."""

    density_altitude_m: float
    air_density_ratio: float
    energy_required_wh: float
    energy_breakdown: EnergyBreakdown
    payload_margin_kg: float
    all_up_mass_kg: float
    ground_speed_mps: float
    effective_hover_power_w: float
    battery_check: BatteryCheck
    safety_flags: SafetyFlags


class PlanResponse(BaseModel):
    """The complete result of a mission planning run."""

    is_viable: bool
    calculations: Calculations | None
    weather: WeatherReading | None
    report: str
    thread_id: str
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str
    service: str
    version: str


class AircraftSummary(BaseModel):
    """Catalog entry describing a selectable airframe."""

    id: str
    name: str
    max_payload_kg: float
    battery_wh: float
    max_wind_mps: float
    max_temp_c: float


class PayloadSummary(BaseModel):
    """Catalog entry describing a selectable payload."""

    id: str
    name: str
    weight_kg: float
    power_draw_w: float


class ReadinessResponse(BaseModel):
    """Readiness probe payload."""

    ready: bool
    database: str
    checkpointer: str


class ThreadStateResponse(BaseModel):
    """Persisted state for a previously planned mission thread."""

    thread_id: str
    found: bool
    is_viable: bool | None
    report: str | None
    calculations: Calculations | None
    weather: WeatherReading | None
