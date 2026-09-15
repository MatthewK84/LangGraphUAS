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
    BLUE_LIST_SNAPSHOT_UNAVAILABLE = "BLUE_LIST_SNAPSHOT_UNAVAILABLE"
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
