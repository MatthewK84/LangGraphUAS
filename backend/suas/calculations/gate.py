"""The operational gate.

A plan is advisory unless every input behind it is good enough to fly on. This
module decides that, and it decides it in the backend: a client may ask for
operational, and the gate answers. Nothing a client or a language model sends
can grant the mode.

The gate fails closed. A condition this codebase cannot yet verify is a blocker,
not a pass -- an unchecked condition and a satisfied one are different things,
and only one of them is safe to treat as met. Several conditions below are in
that state today, which means operational is currently unreachable. That is the
honest position while reference power figures are unsourced estimates, and each
blocker names the issue that retires it.
"""

from dataclasses import dataclass

from suas.schemas.assessment import AssessmentMode, Blocker


@dataclass(frozen=True)
class GateInputs:
    """The facts the operational gate decides on."""

    weather_is_live: bool
    weather_degraded: bool
    assessment_is_complete: bool


def operational_blockers(inputs: GateInputs) -> list[Blocker]:
    """Return every reason this plan cannot be operational, in a stable order."""
    blockers: list[Blocker] = []
    if not inputs.weather_is_live:
        blockers.append(Blocker.WEATHER_NOT_LIVE)
    if inputs.weather_degraded:
        blockers.append(Blocker.WEATHER_DEGRADED)
    if not inputs.assessment_is_complete:
        blockers.append(Blocker.ASSESSMENT_INCOMPLETE)

    # Not yet verifiable. Reference performance figures carry no provenance, no
    # citation is resolved against a datasheet, and no Blue List snapshot is
    # stored, so none of these can be asserted. Each is retired by the issue
    # named beside it, at which point it becomes a real check rather than a
    # standing blocker.
    blockers.append(Blocker.POWER_PROVENANCE_UNAVAILABLE)  # #38
    blockers.append(Blocker.CITATIONS_UNAVAILABLE)  # #38
    blockers.append(Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE)  # split out of #37
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
