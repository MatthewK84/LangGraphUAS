"""The operational gate.

A plan is advisory unless every input behind it is good enough to fly on. This
module decides that, and it decides it in the backend: a client may ask for
operational, and the gate answers. Nothing a client or a language model sends
can grant the mode.

The gate fails closed. A condition this codebase cannot yet verify is a blocker,
not a pass -- an unchecked condition and a satisfied one are different things,
and only one of them is safe to treat as met. One condition is still in that
state, which means operational remains unreachable: no Blue List snapshot is
stored, so configuration clearance cannot be asserted.

Provenance is now checked for real. Power figures in the bundled data are
derived or estimated rather than read from a datasheet, so
POWER_NOT_OPERATIONAL_GRADE fires on every plan today -- but it fires because
the numbers were examined and found wanting, not because nobody looked.
"""

from dataclasses import dataclass
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

    # Still not verifiable: no Blue List snapshot is stored, so configuration
    # clearance cannot be asserted at all. Retired by the snapshot work split out
    # of #37, at which point this becomes a real check rather than a standing
    # blocker.
    blockers.append(Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE)
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
