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
