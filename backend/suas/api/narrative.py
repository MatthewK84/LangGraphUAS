"""Why a published brief is the model's, or the template.

Derived from state the report node already writes (``report`` and
``seal_violations``). The report node's writable set is not widened, and
``graph/seal.py`` is not changed: a withheld figure is already recorded as
``unsupported_numeric:<literal> <unit>``.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from suas.api.report_source import report_source
from suas.schemas.responses import ReportSource, UngroundedNumeric

_UNSUPPORTED: Final[str] = "unsupported_numeric:"
_CONTRADICTION: Final[str] = "contradiction:"
REASON_UNGROUNDED: Final[str] = "not found in the sealed result"
REASON_CONTRADICTION: Final[str] = "the brief contradicted the sealed decision"

# Display forms for units ``unsupported_numerics`` may emit, after lowercasing.
_UNIT_DISPLAY: Final[dict[str, str]] = {
    "wh": "Wh",
    "w": "W",
    "mah": "mAh",
    "v": "V",
    "a": "A",
    "m/s": "m/s",
    "km/h": "km/h",
    "kph": "kph",
    "mph": "mph",
    "km": "km",
    "m": "m",
    "min": "min",
    "s": "s",
    "%": "%",
    "c": "C",
}


def _display_unit(raw: str) -> str:
    """Return the conventional casing for a sealed unit token."""
    return _UNIT_DISPLAY.get(raw.lower(), raw)


def ungrounded_from_violations(violations: Sequence[object]) -> list[UngroundedNumeric]:
    """Parse ``unsupported_numeric:`` seal violations into value and unit."""
    found: list[UngroundedNumeric] = []
    for item in violations:
        text = str(item)
        if not text.startswith(_UNSUPPORTED):
            continue
        rest = text[len(_UNSUPPORTED) :].strip()
        literal, _, unit = rest.partition(" ")
        if literal and unit:
            found.append(UngroundedNumeric(value=literal, unit=_display_unit(unit)))
    return found


def narrative_reason(violations: Sequence[object]) -> str:
    """Return a short reason when a model narrative was withheld."""
    texts = [str(item) for item in violations]
    if any(text.startswith(_UNSUPPORTED) for text in texts):
        return REASON_UNGROUNDED
    if any(text.startswith(_CONTRADICTION) for text in texts):
        return REASON_CONTRADICTION
    return ""


def narrative_fields(
    state: Mapping[str, object],
) -> tuple[ReportSource, list[UngroundedNumeric], str]:
    """Return ``narrative_source``, ungrounded figures, and a short reason."""
    violations = state.get("seal_violations") or []
    if not isinstance(violations, (list, tuple)):
        violations = []
    return (
        report_source(state),
        ungrounded_from_violations(violations),
        narrative_reason(violations),
    )
