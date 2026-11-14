"""The operational gate.

A plan is advisory unless every input behind it is good enough to fly on. This
module decides that, and it decides it in the backend: a client may ask for
operational, and the gate answers. Nothing a client or a language model sends
can grant the mode.

The gate fails closed. A condition this codebase cannot yet verify is a blocker,
not a pass -- an unchecked condition and a satisfied one are different things,
and only one of them is safe to treat as met.

The Blue UAS snapshot is a real check: a missing or unreadable snapshot is
BLUE_LIST_SNAPSHOT_UNAVAILABLE, and a snapshot older than the configured
maximum age is BLUE_LIST_SNAPSHOT_STALE. Advisory plans still run in both
cases. Provenance of the energy-budget figures is also checked for real.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from suas.schemas.assessment import AssessmentMode, Blocker
from suas.schemas.provenance import FieldProvenance

# Numbers that feed the energy budget. An operational plan needs these to come
# from a manufacturer document or a measured flight log; nothing else is good
# enough to fly on.
POWER_FIELDS_AIRCRAFT: Final[frozenset[str]] = frozenset(
    {"hover_power_w", "cruise_power_w", "battery_wh"}
)
POWER_FIELDS_PAYLOAD: Final[frozenset[str]] = frozenset({"power_draw_w"})

# Every numeric field that must carry a provenance record at all. Missing
# provenance is a different failure from weak provenance, and they are reported
# separately: one means nobody wrote it down, the other means what was written
# down is not good enough.
REQUIRED_PROVENANCE_AIRCRAFT: Final[frozenset[str]] = frozenset(
    {
        "weight_kg",
        "max_payload_kg",
        "battery_wh",
        "max_wind_mps",
        "cruise_speed_mps",
        "hover_power_w",
        "cruise_power_w",
        "max_temp_c",
        "min_temp_c",
    }
)
REQUIRED_PROVENANCE_PAYLOAD: Final[frozenset[str]] = frozenset({"weight_kg", "power_draw_w"})


def provenance_is_complete(
    aircraft: dict[str, FieldProvenance],
    payload: dict[str, FieldProvenance],
) -> bool:
    """Return whether every field that must be accounted for has a record."""
    return aircraft.keys() >= REQUIRED_PROVENANCE_AIRCRAFT and (
        payload.keys() >= REQUIRED_PROVENANCE_PAYLOAD
    )


def power_is_operational_grade(
    aircraft: dict[str, FieldProvenance],
    payload: dict[str, FieldProvenance],
) -> bool:
    """Return whether every energy-budget figure comes from a datasheet or a log."""
    records = [aircraft.get(field) for field in sorted(POWER_FIELDS_AIRCRAFT)]
    records += [payload.get(field) for field in sorted(POWER_FIELDS_PAYLOAD)]
    return all(record is not None and record.is_operational_grade for record in records)


@dataclass(frozen=True)
class GateInputs:
    """The facts the operational gate decides on."""

    weather_is_live: bool
    weather_degraded: bool
    assessment_is_complete: bool
    provenance_is_complete: bool = False
    power_is_operational_grade: bool = False
    # True when this configuration has corpus chunks awaiting human review.
    # Default False: no corpus at all is not the same as a poisoned one.
    corpus_quarantined: bool = False
    # The pinned Blue UAS snapshot. Missing or unreadable is not the same as
    # stale: one means clearance cannot be asserted, the other means the
    # assertion would be about the past.
    blue_list_snapshot_available: bool = False
    blue_list_snapshot_stale: bool = False


def blue_list_snapshot_is_stale(
    fetched_at: datetime | None,
    *,
    now: datetime,
    max_age_s: float,
) -> bool:
    """Return whether a known snapshot is older than the configured age.

    A missing date is not stale: the caller must treat that as unavailable.
    Age equal to the threshold is still current; one second over is stale.
    """
    if fetched_at is None:
        return False
    return (now - fetched_at).total_seconds() > max_age_s


def operational_blockers(inputs: GateInputs) -> list[Blocker]:
    """Return every reason this plan cannot be operational, in a stable order."""
    blockers: list[Blocker] = []
    if not inputs.weather_is_live:
        blockers.append(Blocker.WEATHER_NOT_LIVE)
    if inputs.weather_degraded:
        blockers.append(Blocker.WEATHER_DEGRADED)
    if not inputs.assessment_is_complete:
        blockers.append(Blocker.ASSESSMENT_INCOMPLETE)

    if not inputs.provenance_is_complete:
        blockers.append(Blocker.PROVENANCE_INCOMPLETE)
    if not inputs.power_is_operational_grade:
        blockers.append(Blocker.POWER_NOT_OPERATIONAL_GRADE)
    if inputs.corpus_quarantined:
        blockers.append(Blocker.CORPUS_QUARANTINED)
    if not inputs.blue_list_snapshot_available:
        blockers.append(Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE)
    elif inputs.blue_list_snapshot_stale:
        blockers.append(Blocker.BLUE_LIST_SNAPSHOT_STALE)
    return blockers


def resolve_mode(requested: AssessmentMode, blockers: list[Blocker]) -> AssessmentMode:
    """Return the mode this plan actually carries.

    A request for operational with outstanding blockers is downgraded rather
    than refused: the assessment still ran, and the caller is better served by
    the advisory result plus the reasons than by an error with no content.
    """
    if requested is AssessmentMode.OPERATIONAL and not blockers:
        return AssessmentMode.OPERATIONAL
    return AssessmentMode.ADVISORY
