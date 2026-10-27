"""Whether a language model wrote the brief in a plan response.

Derived where the response is built, not stored by the report node: the seal
(``suas.graph.seal.REPORT_NODE_WRITABLE``) lets that node write only ``report``
and ``seal_violations``, and widening it is a change to safety code. Every brief
written by code comes from a named text in this codebase, so membership in that
set is an exact test, and a brief the seal withheld is known by its violations.
"""

from collections.abc import Mapping
from typing import Any, Final

from suas.graph.nodes import (
    ABORTED_REPORT,
    INVALID_AIRCRAFT_REPORT,
    narrative_unavailable_report,
    validation_failed_report,
)
from suas.schemas.responses import ReportSource
from suas.services.llm import fallback_report

_DETERMINISTIC: Final[frozenset[str]] = frozenset(
    {ABORTED_REPORT, INVALID_AIRCRAFT_REPORT}
    | {
        render(is_viable)
        for render in (fallback_report, narrative_unavailable_report, validation_failed_report)
        for is_viable in (True, False)
    }
)


def report_source(state: Mapping[str, Any]) -> ReportSource:
    """Return ``model`` only for prose the language model wrote and the seal kept."""
    report: str = str(state.get("report") or "")
    if not report or state.get("seal_violations") or report in _DETERMINISTIC:
        return "deterministic"
    return "model"
