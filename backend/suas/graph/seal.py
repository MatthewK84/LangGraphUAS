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

from suas.schemas.assessment import Decision, DeterministicAssessment

# The only state keys the report node may write. Enforced by test, because the
# refactor that quietly adds a seventh key is the one worth catching.
REPORT_NODE_WRITABLE: Final[frozenset[str]] = frozenset({"report", "seal_violations"})

# The only keys a brief may contribute. Anything else is dropped.
BRIEF_FIELDS: Final[frozenset[str]] = frozenset({"brief_markdown", "suggested_contingencies"})

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


def seal_brief(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return the allowlisted brief fields and the sealed keys that were dropped.

    Args:
        raw: Parsed model output.

    Returns:
        A pair of (kept fields, names of sealed fields the model tried to write).
        Unknown keys that are not sealed are dropped silently; they are noise,
        not an attempt to author a decision.
    """
    kept: dict[str, Any] = {key: value for key, value in raw.items() if key in BRIEF_FIELDS}
    violations: list[str] = sorted(key for key in raw if key in SEALED_FIELDS)
    return kept, violations


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
