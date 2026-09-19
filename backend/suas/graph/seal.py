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
from typing import Any, Final

from pydantic import ValidationError

from suas.schemas.assessment import Decision, DeterministicAssessment
from suas.schemas.brief import BriefOutput

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


def _supported_values(supporting_text: str) -> set[float]:
    """Return every number appearing in text the brief is allowed to draw from."""
    return {float(match) for match in _ANY_NUMERIC.findall(supporting_text)}


def _is_supported(literal: str, supported: set[float]) -> bool:
    """Return whether a prose number is a rounding of some supported number.

    Rounding is legitimate: a calculator producing 119.94 W and prose saying
    "120 W" is the model writing readably, not inventing. Matching at the
    precision the prose chose accepts that without accepting 90 W.
    """
    decimals: int = len(literal.partition(".")[2])
    target: float = float(literal)
    return any(round(value, decimals) == target for value in supported)


def unsupported_numerics(prose: str, supporting_text: str) -> list[str]:
    """Return unit-bearing numbers in prose that trace to nothing.

    The model is told to state no number that is not in the assessment or
    verbatim in evidence; this verifies it rather than trusting it. Every
    instance is returned so the caller can log each one -- see the
    unsupported_numeric_rate row in docs/rag-eval.md.

    **This is a tripwire, not a proof, and it is unit-blind.** Matching is on the
    numeric value alone, so a wind speed of 6.9 m/s in the supporting text will
    accept "7 W" in prose. Making it unit-aware would mean inferring units from
    JSON key suffixes, which cannot work for numbers quoted out of citation text
    -- free prose carries no key. It catches the case it exists for, a wattage
    the calculator never produced, and it will miss a fabricated number that
    happens to collide with an unrelated quantity. The seal is what makes that
    survivable: no number here can change a decision or a stored field.
    """
    supported: set[float] = _supported_values(supporting_text)
    found: list[str] = []
    for literal, unit in _UNIT_NUMERIC.findall(prose):
        if not _is_supported(literal, supported):
            found.append(f"{literal} {unit}")
    return found


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
