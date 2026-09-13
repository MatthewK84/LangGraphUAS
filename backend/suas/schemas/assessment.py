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

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Decision(str, Enum):
    """The three outcomes an assessment can reach.

    ``INSUFFICIENT_DATA`` is deliberately distinct from ``NO_GO``: "we assessed
    this mission and it fails a limit" and "we could not assess this mission"
    are different statements, and collapsing them into one boolean hides the
    second behind the first.
    """

    GO = "go"
    NO_GO = "no_go"
    INSUFFICIENT_DATA = "insufficient_data"


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
    inputs_hash: str
    calculator_version: str

    @property
    def is_viable(self) -> bool:
        """Return whether this assessment permits flight.

        Only ``GO`` does. ``INSUFFICIENT_DATA`` is not viable, because an
        unassessed mission is not a safe one.
        """
        return self.decision is Decision.GO
