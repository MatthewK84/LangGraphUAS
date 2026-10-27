"""Response and computed-result models.

These are the explicit shapes returned to the client and produced by the pure
calculation layer (Principle 8).
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from suas.schemas.alerts import Alert, RecommendedAction, Severity
from suas.schemas.assessment import DeterministicAssessment
from suas.schemas.provenance import Confidence, FieldSource

# Who wrote the brief: deterministic code (no key, a failed call, a brief the
# seal withheld, an abort, nothing written yet) or the language model.
ReportSource = Literal["deterministic", "model"]


class WeatherSource(StrEnum):
    """Provenance of a weather reading.

    Several states rather than two, because "we could not reach the provider",
    "the provider answered with nonsense", and "this is a reading from eight
    minutes ago" are different situations that an operator would act on
    differently. Only the first two below are good enough to fly on; a demo
    fixture never is.
    """

    LIVE = "live"
    """Fetched now, parsed, and complete."""

    CACHED_FRESH = "cached_fresh"
    """A recent reading, still inside its freshness window."""

    CACHED_STALE = "cached_stale"
    """A reading past its freshness window, used because the live fetch failed."""

    FALLBACK = "fallback"
    """Defaults, because the provider could not be reached at all."""

    ERROR = "error"
    """Defaults, because the provider answered and the answer was unusable."""

    FIXTURE = "fixture"
    """A fixed reading from demo mode, never fetched from anything (#97)."""


# The only weather states an operational plan may rest on.
OPERATIONAL_WEATHER: frozenset[WeatherSource] = frozenset(
    {WeatherSource.LIVE, WeatherSource.CACHED_FRESH}
)


class WeatherReading(BaseModel):
    """A point-in-time meteorological reading."""

    temperature_c: float
    wind_speed_mps: float
    wind_gust_mps: float = 0.0
    wind_direction: float
    humidity_percent: float
    conditions: str
    source: WeatherSource = WeatherSource.LIVE
    # When the underlying observation was fetched. None for defaults, which were
    # never fetched from anything.
    fetched_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        """Return whether the reading came from the live provider just now."""
        return self.source is WeatherSource.LIVE

    @property
    def is_operational_grade(self) -> bool:
        """Return whether this reading is good enough for an operational plan."""
        return self.source in OPERATIONAL_WEATHER

    @property
    def degraded(self) -> bool:
        """Return whether this reading is anything less than operational grade."""
        return not self.is_operational_grade


class SafetyFlags(BaseModel):
    """Boolean pass/fail flags for each independent safety constraint."""

    battery_viable: bool
    payload_within_limits: bool
    wind_within_limits: bool
    gust_within_limits: bool
    temperature_within_limits: bool
    pack_temp_within_takeoff_limits: bool
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


class InputBasis(BaseModel):
    """One reference field a W or Wh figure was computed from, as recorded (#96).

    ``value`` and ``unit`` are ``None`` when the catalog keeps no record for the
    field; ``source`` is then ``unknown``, the same reading the summary gives it.
    """

    field: str
    value: float | None
    unit: str | None
    source: FieldSource
    confidence: Confidence
    source_url: str | None = None
    retrieved_at: str | None = None
    notes: str = ""


class NumberProvenance(BaseModel):
    """What one W or Wh figure in ``Calculations`` rests on (#79).

    ``source`` and ``confidence`` are the weakest among ``inputs``, the reference
    fields the figure was computed from. ``operational_grade`` is true only when
    every input is, by the same rule the operational gate applies, so a client
    never has to repeat that rule to know a watt is an estimate.
    """

    source: FieldSource
    confidence: Confidence
    operational_grade: bool
    inputs: list[str]
    basis: list[InputBasis] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """The complete result of a mission planning run.

    ``assessment`` is the authoritative decision. ``is_viable`` is retained as a
    derived convenience for existing clients and means exactly
    ``assessment.decision == "go"``; it will be removed once the review-and-ack
    flow lands and the dashboard reads the assessment directly.
    """

    is_viable: bool
    assessment: DeterministicAssessment | None = None
    # True while the run is paused at the review step. A brief does not exist
    # yet, and will not until a human signs the assessment above.
    awaiting_ack: bool = False
    aborted: bool = False
    calculations: Calculations | None
    # One entry per W and Wh figure in ``calculations``, keyed by its dotted path.
    provenance: dict[str, NumberProvenance] = Field(default_factory=dict)
    weather: WeatherReading | None
    report: str
    report_source: ReportSource = "deterministic"
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
    migrations: str = Field(
        description="ok, pending (schema behind the code), not_tracked (local create_all), "
        "or unknown (database unavailable)"
    )
    checkpointer: str


class ThreadStateResponse(BaseModel):
    """Persisted state for a previously planned mission thread."""

    thread_id: str
    found: bool
    is_viable: bool | None
    report: str | None
    calculations: Calculations | None
    provenance: dict[str, NumberProvenance] = Field(default_factory=dict)
    weather: WeatherReading | None
    assessment: DeterministicAssessment | None = None
    awaiting_ack: bool = False


class PowerEstimateSummary(BaseModel):
    """A measured power figure derived from a flight log."""

    median_w: float
    sample_count: int
    confidence: str


class FlightLogResponse(BaseModel):
    """The outcome of ingesting one flight log.

    ``applied_fields`` is empty unless the caller asked for the estimates to be
    written into the airframe and they cleared the sample-count bar. An estimate
    that did not clear it still appears above, where it is visible without being
    load-bearing.
    """

    log_id: str
    airframe_id: str
    row_count: int
    rejected_rows: int
    hover: PowerEstimateSummary | None = None
    cruise: PowerEstimateSummary | None = None
    applied_fields: list[str] = Field(default_factory=list)


class LiveEnergyView(BaseModel):
    """The energy picture computed from live telemetry."""

    available_wh: float
    reserve_wh: float
    required_wh: float
    residual_wh: float
    temperature_factor: float


class ReplanResponse(BaseModel):
    """The result of comparing a briefed plan against live telemetry.

    ``operational_ok`` is false whenever any alert fired, including a watch. An
    alert means something could not be confirmed, and an unconfirmed replan is
    advice rather than clearance.
    """

    thread_id: str
    parent_thread_id: str
    severity: Severity
    recommended_action: RecommendedAction
    operational_ok: bool
    live_energy: LiveEnergyView | None = None
    briefed_margin_wh: float | None = None
    snapshot_age_s: float
    alerts: list[Alert] = Field(default_factory=list)
