"""The barrier between language-model output and the sealed assessment.

Two controls live here, and they are separate on purpose.

``seal_brief`` is a positive allowlist: model output keeps only the fields a
brief is allowed to contain, and everything else is dropped rather than merged.
Today the report service returns prose, so nothing reaches it with keys at all;
it is in place for the structured brief output that follows, because the moment
to build the barrier is before there is something to carry through it.

``find_contradiction`` is a tripwire on the prose itself: a brief that says the
mission is good to fly when the calculator said it is not. That cannot change
the decision -- the decision is rendered from the sealed object on a different
data path -- but it is a signal that something upstream is wrong, and it is
counted rather than swallowed.
"""

import re
from collections.abc import Sequence
from typing import Any, Final, NamedTuple

from pydantic import ValidationError

from suas.schemas.assessment import Decision, DeterministicAssessment
from suas.schemas.brief import BriefOutput
from suas.schemas.responses import Calculations

# The only state keys the report node may write. Enforced by test, because the
# refactor that quietly adds a seventh key is the one worth catching.
REPORT_NODE_WRITABLE: Final[frozenset[str]] = frozenset({"report", "seal_violations"})

# The only keys a brief may contribute. Anything else is dropped.
BRIEF_FIELDS: Final[frozenset[str]] = frozenset(BriefOutput.model_fields)

# Fields the calculator owns. A model emitting one of these is not a formatting
# quirk to tidy up; it is the failure this module exists to catch, so these are
# reported separately from ordinary unknown keys.
SEALED_FIELDS: Final[frozenset[str]] = frozenset(DeterministicAssessment.model_fields) | frozenset(
    {
        "is_viable",
        "assessment_mode",
        "requested_mode",
        "energy",
        "energy_required_wh",
        "energy_breakdown",
        "hover_power_w",
        "effective_hover_power_w",
        "cruise_power_w",
        "battery_check",
        "safety_flags",
        "limits",
        "all_up_mass_kg",
        "payload_margin_kg",
        "density_altitude_m",
        "ground_speed_mps",
    }
)

# "no-go" contains "go". Scrub the negated forms before looking for go-language,
# or the deterministic fallback text ("Mission status: NO-GO.") reports itself.
_NEGATED: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:no[-\s]?go"
    r"|(?:do not|don't|cannot|can't|must not|not|never|no)\s+"
    r"(?:go|fly|flying|launch|proceed\w*|cleared))\b"
)

_GO_LANGUAGE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(go"
    r"|cleared (?:for|to) (?:flight|fly|takeoff|launch)"
    r"|safe to (?:fly|launch|proceed)"
    r"|proceed with (?:the )?(?:flight|mission))\b"
)


def seal_brief(raw: dict[str, Any]) -> tuple[BriefOutput | None, list[str]]:
    """Return the parsed brief and the sealed keys the model tried to write.

    Keys outside the allowlist are dropped before validation rather than after,
    so a model that pads its output with noise still produces a usable brief
    while one that tries to author a decision is recorded as having done so.

    Returns ``None`` for the brief when what remains cannot be validated. There
    is deliberately no retry: a model that returns an invalid object does not get
    to negotiate its way to a valid-looking one.
    """
    violations: list[str] = sorted(key for key in raw if key in SEALED_FIELDS)
    kept: dict[str, Any] = {key: value for key, value in raw.items() if key in BRIEF_FIELDS}
    try:
        return BriefOutput.model_validate(kept), violations
    except ValidationError:
        return None, violations


def resolve_citations(
    cited_chunk_ids: list[str],
    retrieved_chunk_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Split cited ids into those actually retrieved and those invented.

    A model that cites a chunk nobody gave it has not made a formatting mistake.
    Either it is repeating an id from somewhere it should not have, or it made one
    up; both mean the citation points at nothing, and a citation that cannot be
    followed is worse than none because it looks like evidence.

    Returns:
        A pair of (resolvable ids, invented ids). Invented ids are returned rather
        than discarded so the caller can count them.
    """
    kept: list[str] = [item for item in cited_chunk_ids if item in retrieved_chunk_ids]
    invented: list[str] = [item for item in cited_chunk_ids if item not in retrieved_chunk_ids]
    return kept, invented


# Numbers that carry a unit are the ones that can fly an aircraft into the
# ground. A bare integer in prose ("the 3 limiting factors") is not a claim about
# the world; "90 W" is.
_UNIT_NUMERIC: Final[re.Pattern[str]] = re.compile(
    # (?!\w) rather than \b as the trailing guard: \b after "%" requires a word
    # character next, so "55 %." never matched and percentages went unchecked.
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(Wh|W|mAh|V|A|m/s|km/h|kph|mph|km|m|min|s|%|C)(?!\w)"
)
_ANY_NUMERIC: Final[re.Pattern[str]] = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")


class GroundedFigure(NamedTuple):
    """A number from the seal, the calculator, or unit-bearing supporting text."""

    value: float
    unit: str


# Longer suffixes first so _wh wins over _w and _mps wins over _s and _m.
_KEY_UNITS: Final[tuple[tuple[str, str], ...]] = (
    ("_wh", "Wh"),
    ("_w", "W"),
    ("_mps", "m/s"),
    ("_kmh", "km/h"),
    ("_kph", "kph"),
    ("_mph", "mph"),
    ("_mah", "mAh"),
    ("_kg", "kg"),
    ("_percent", "%"),
    ("_min", "min"),
    ("_c", "C"),
    ("_s", "s"),
    ("_m", "m"),
)

_ABS_TOLERANCE: Final[float] = 0.005


def _supported_values(supporting_text: str) -> set[float]:
    """Return every number appearing in text the brief is allowed to draw from."""
    return {float(match) for match in _ANY_NUMERIC.findall(supporting_text)}


def _unit_for_key(key: str) -> str | None:
    """Return the unit implied by a JSON key suffix, if one is known."""
    lowered = key.lower()
    for suffix, unit in _KEY_UNITS:
        if lowered.endswith(suffix):
            return unit
    return None


def figures_from_mapping(value: object, key: str = "") -> list[GroundedFigure]:
    """Return unit-tagged figures walked out of a mapping or model dump."""
    if isinstance(value, dict):
        return _figures_from_items(value)
    if isinstance(value, (list, tuple)):
        return _figures_from_sequence(value, key)
    return _figure_from_scalar(value, key)


def _figures_from_items(mapping: dict[object, object]) -> list[GroundedFigure]:
    found: list[GroundedFigure] = []
    for child_key, child in mapping.items():
        found.extend(figures_from_mapping(child, str(child_key)))
    return found


def _figures_from_sequence(
    values: list[object] | tuple[object, ...], key: str
) -> list[GroundedFigure]:
    found: list[GroundedFigure] = []
    for child in values:
        found.extend(figures_from_mapping(child, key))
    return found


def _figure_from_scalar(value: object, key: str) -> list[GroundedFigure]:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return []
    if isinstance(value, (int, float)):
        unit = _unit_for_key(key)
        if unit:
            return [GroundedFigure(float(value), unit)]
    return []


def figures_from_text(text: str) -> list[GroundedFigure]:
    """Return unit-bearing numbers found in supporting prose or citations."""
    return [GroundedFigure(float(literal), unit) for literal, unit in _UNIT_NUMERIC.findall(text)]


def _is_supported(literal: str, supported: set[float]) -> bool:
    """Return whether a prose number is a rounding of some supported number.

    Rounding is legitimate: a calculator producing 119.94 W and prose saying
    "120 W" is the model writing readably, not inventing. Matching at the
    precision the prose chose accepts that without accepting 90 W.
    """
    decimals: int = len(literal.partition(".")[2])
    target: float = float(literal)
    return any(round(value, decimals) == target for value in supported)


def _figure_matches(literal: str, unit: str, figure: GroundedFigure) -> bool:
    """Return whether one sealed figure supports a prose number of the same unit."""
    if figure.unit != unit:
        return False
    decimals: int = len(literal.partition(".")[2])
    target: float = float(literal)
    if round(figure.value, decimals) == target:
        return True
    return abs(figure.value - target) <= _ABS_TOLERANCE


def unsupported_numerics(
    prose: str,
    supporting_text: str,
    *,
    figures: Sequence[GroundedFigure] | None = None,
) -> list[str]:
    """Return unit-bearing numbers in prose that trace to nothing.

    When ``figures`` is provided, matching is unit-aware: "3 W" is not
    supported by a wind speed of 3 m/s. Rounding to the precision the prose
    chose remains legitimate (119.94 W may be written "120 W"), and a
    0.005 absolute tolerance covers a figure restated one tick off. Unit-
    bearing numbers in ``supporting_text`` (citation excerpts) are also
    accepted. The text-only, unit-blind path is kept for callers that have
    not yet collected structured figures.

    Every instance is returned so the caller can log each one -- see the
    unsupported_numeric_rate row in docs/rag-eval.md. This is still a
    tripwire, not a proof: a fabricated number that collides with a same-
    unit sealed figure will slip through. The seal is what makes that
    survivable: no number here can change a decision or a stored field.
    """
    if figures is not None:
        allowed: list[GroundedFigure] = [*figures, *figures_from_text(supporting_text)]
        found: list[str] = []
        for literal, unit in _UNIT_NUMERIC.findall(prose):
            if not any(_figure_matches(literal, unit, item) for item in allowed):
                found.append(f"{literal} {unit}")
        return found
    supported: set[float] = _supported_values(supporting_text)
    found = []
    for literal, unit in _UNIT_NUMERIC.findall(prose):
        if not _is_supported(literal, supported):
            found.append(f"{literal} {unit}")
    return found


def ground_narrative(
    prose: str,
    assessment: DeterministicAssessment,
    calculations: Calculations | None,
    extra_text: str = "",
) -> tuple[str, list[str]]:
    """Return a publishable brief, or the template if the prose invents a number.

    Figures are taken from the sealed assessment and the calculator output.
    Citation or weather text can be passed as ``extra_text``.
    """
    sourced: list[GroundedFigure] = figures_from_mapping(assessment.model_dump(mode="json"))
    if calculations is not None:
        sourced.extend(figures_from_mapping(calculations.model_dump(mode="json")))
    invented: list[str] = unsupported_numerics(prose, extra_text, figures=sourced)
    if invented:
        return render_template_brief(assessment), invented
    return prose, []


def render_template_brief(assessment: DeterministicAssessment) -> str:
    """Return a brief built only from the sealed assessment.

    Used when generated prose is suppressed. Deleting the brief instead would
    leave an operator with a verdict and no explanation at exactly the moment
    something upstream is behaving oddly, so the sealed object writes its own.
    """
    verdict: str = {
        Decision.GO: "GO",
        Decision.NO_GO: "NO-GO",
        Decision.INSUFFICIENT_DATA: "NOT ASSESSED",
    }[assessment.decision]
    lines: list[str] = [
        f"Mission status: {verdict} ({assessment.mode.value}).",
        "",
        "The generated brief was withheld because it disagreed with this "
        "assessment. What follows comes from the calculator alone.",
        "",
    ]
    if assessment.reasons:
        lines.append("Limiting factors:")
        lines.extend(f"- {reason}" for reason in assessment.reasons)
        lines.append("")
    if assessment.blockers:
        lines.append("Blocking operational use:")
        lines.extend(f"- {blocker.value}" for blocker in assessment.blockers)
        lines.append("")
    lines.append(f"Calculator {assessment.calculator_version}, inputs {assessment.inputs_hash}.")
    return "\n".join(lines)


def find_contradiction(prose: str, decision: Decision) -> str | None:
    """Return the go-language found in prose that contradicts the decision.

    Returns None when the decision is GO, or when no contradiction is present.
    This is a tripwire and will occasionally fire on an innocent phrasing, which
    is why it reports rather than deletes: a false positive costs a log line,
    and a missed contradiction costs an operator's trust in the brief.
    """
    if decision is Decision.GO:
        return None
    scrubbed: str = _NEGATED.sub(" ", prose)
    match = _GO_LANGUAGE.search(scrubbed)
    return match.group(0) if match else None
