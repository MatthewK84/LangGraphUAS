"""Where a number came from.

Every performance figure in the bundled reference data carries one of these. The
point is not bookkeeping: the operational gate reads ``source``, and a plan may
only carry operational weight when the numbers behind it come from a manufacturer
document or a measured flight log.

The source values are deliberately finer-grained than "published or not". A
figure copied from a specification summary is not the same as one read out of
the manufacturer's own datasheet, and recording them identically would overstate
what this project knows. ``UNKNOWN`` exists for the same reason: when the record
does not say where a number came from, saying so beats guessing a category.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Sources good enough to fly on. Everything else blocks operational mode.
OPERATIONAL_GRADE: frozenset[str] = frozenset({"datasheet", "flight_log"})


class FieldSource(StrEnum):
    """How a reference figure was obtained."""

    DATASHEET = "datasheet"
    """Read from the manufacturer's own published document."""

    FLIGHT_LOG = "flight_log"
    """Measured from recorded flight telemetry."""

    SECONDARY = "secondary"
    """Published figure taken from a specification summary, not the primary document."""

    DERIVED = "derived"
    """Computed from other fields by a formula recorded in ``notes``."""

    ESTIMATE = "estimate"
    """An engineering estimate. ``notes`` must say what it rests on."""

    UNKNOWN = "unknown"
    """Provenance is not recorded. Distinct from an estimate: nobody vouched for this."""


class Confidence(StrEnum):
    """How much weight to put on a figure."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FieldProvenance(BaseModel):
    """The provenance record attached to a single numeric field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float
    unit: str = Field(min_length=1)
    source: FieldSource
    source_url: str | None = None
    retrieved_at: str | None = None
    confidence: Confidence = Confidence.LOW
    notes: str = ""

    @property
    def is_operational_grade(self) -> bool:
        """Return whether this figure is good enough for an operational plan."""
        return self.source.value in OPERATIONAL_GRADE
