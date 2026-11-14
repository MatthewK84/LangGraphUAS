"""The sealed deterministic assessment.

This is the object the rest of the system treats as the decision. It is
constructed only by ``suas.calculations`` and is never assembled from, merged
with, or corrected by language-model output. The graph passes it to the report
node as read-only context; ``suas.graph.seal`` enforces that the node cannot
write any field defined here.

``inputs_hash`` and ``calculator_version`` exist so a later acknowledgement can
be bound to exactly what was assessed: if either changes, a prior sign-off no
longer applies to the current numbers.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Decision(StrEnum):
    """The three outcomes an assessment can reach.

    ``INSUFFICIENT_DATA`` is deliberately distinct from ``NO_GO``: "we assessed
    this mission and it fails a limit" and "we could not assess this mission"
    are different statements, and collapsing them into one boolean hides the
    second behind the first.
    """

    GO = "go"
    NO_GO = "no_go"
    INSUFFICIENT_DATA = "insufficient_data"


class AssessmentMode(StrEnum):
    """How much weight a plan is allowed to carry.

    ``ADVISORY`` is planning support. ``OPERATIONAL`` asserts the inputs were
    good enough to fly on, and is granted by the backend rather than requested
    by the client: a caller asks, the gate decides.
    """

    ADVISORY = "advisory"
    OPERATIONAL = "operational"


class Blocker(StrEnum):
    """Machine-readable reasons a plan could not be operational.

    Each is a fact about the inputs, not about the mission. A no-go with no
    blockers is a fully-informed refusal; an advisory plan with blockers is a
    statement that we did not know enough to be sure either way.
    """

    WEATHER_NOT_LIVE = "WEATHER_NOT_LIVE"
    WEATHER_DEGRADED = "WEATHER_DEGRADED"
    ASSESSMENT_INCOMPLETE = "ASSESSMENT_INCOMPLETE"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
    POWER_NOT_OPERATIONAL_GRADE = "POWER_NOT_OPERATIONAL_GRADE"
    FIELD_NOT_OPERATIONAL_GRADE = "FIELD_NOT_OPERATIONAL_GRADE"
    CONFIGURATION_NOT_LAB_OPERATIONAL = "CONFIGURATION_NOT_LAB_OPERATIONAL"
    BLUE_LIST_SNAPSHOT_UNAVAILABLE = "BLUE_LIST_SNAPSHOT_UNAVAILABLE"
    BLUE_LIST_SNAPSHOT_STALE = "BLUE_LIST_SNAPSHOT_STALE"
    CORPUS_QUARANTINED = "CORPUS_QUARANTINED"


class DeterministicAssessment(BaseModel):
    """A decision, its reasons, and the inputs and code version behind it.

    Frozen: once the calculator has produced one, no later stage edits it in
    place. A changed assessment is a new assessment with a new hash.

    It deliberately does not embed ``Calculations``. The energy and limit figures
    travel beside it on the response, and re-embedding them here would duplicate
    the payload on the wire and make this module import the response models it is
    imported by. Nothing is lost: ``inputs_hash`` and ``calculator_version``
    together identify exactly which numbers this decision came from.
    """

    model_config = ConfigDict(frozen=True)

    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    mode: AssessmentMode = AssessmentMode.ADVISORY
    blockers: list[Blocker] = Field(default_factory=list)
    inputs_hash: str
    calculator_version: str

    @property
    def is_operational(self) -> bool:
        """Return whether this plan carries operational weight."""
        return self.mode is AssessmentMode.OPERATIONAL

    @property
    def is_viable(self) -> bool:
        """Return whether this assessment permits flight.

        Only ``GO`` does. ``INSUFFICIENT_DATA`` is not viable, because an
        unassessed mission is not a safe one.
        """
        return self.decision is Decision.GO


# Operator-facing sentences for each blocker. The sealed assessment still
# carries the machine-readable code; this text is for the dashboard and docs.
BLOCKER_REASONS: dict[Blocker, str] = {
    Blocker.WEATHER_NOT_LIVE: "Weather is not a live or fresh cached observation.",
    Blocker.WEATHER_DEGRADED: "The weather reading is degraded.",
    Blocker.ASSESSMENT_INCOMPLETE: "The mission could not be fully assessed.",
    Blocker.PROVENANCE_INCOMPLETE: "A required figure has no provenance record.",
    Blocker.POWER_NOT_OPERATIONAL_GRADE: (
        "An energy-budget figure is not from a datasheet or flight log."
    ),
    Blocker.FIELD_NOT_OPERATIONAL_GRADE: (
        "A required figure is not from a datasheet or flight log."
    ),
    Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL: (
        "Operational mode is only considered for the lab configuration "
        "Freefly Astro Max + Sony ILX-LR1."
    ),
    Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE: (
        "No usable Blue UAS snapshot is stored, so configuration clearance cannot be asserted."
    ),
    Blocker.BLUE_LIST_SNAPSHOT_STALE: (
        "The pinned Blue UAS snapshot is older than the configured maximum age, "
        "so an operational claim would describe the past. Verify the current list "
        "at bluelist.dcma.mil before flight."
    ),
    Blocker.CORPUS_QUARANTINED: "Corpus chunks for this configuration are awaiting review.",
}


def blocker_reason(blocker: Blocker) -> str:
    """Return the operator-facing sentence for a blocker."""
    return BLOCKER_REASONS[blocker]
