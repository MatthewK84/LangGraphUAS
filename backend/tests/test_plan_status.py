"""The status block on PLAN-90 must describe the gate that exists.

A status block is a claim about the system, and the claim most likely to rot is
the list of blockers: someone retires one in `gate.py` and the plan still names
it. These tests read both and compare, so the doc cannot outlive the code.
"""

import re
from pathlib import Path
from typing import Final

from suas.calculations.gate import GateInputs, operational_blockers
from suas.schemas.assessment import Blocker

PLAN: Final[Path] = Path(__file__).resolve().parent.parent.parent / "docs" / "PLAN-90.md"
_BACKTICKED: Final[re.Pattern[str]] = re.compile(r"`([A-Z][A-Z_]+)`")


def _status_block() -> str:
    """Return the text of the status section, up to the next top-level heading."""
    text = PLAN.read_text(encoding="utf-8")
    start = text.index("## Status as of ")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_the_plan_carries_a_dated_status_block() -> None:
    assert re.search(r"## Status as of \d{4}-\d{2}-\d{2}", _status_block())


def test_the_status_block_answers_the_three_questions() -> None:
    """A stranger should find week, blockers and next steps without scrolling."""
    block = _status_block()

    assert "### On main" in block
    assert "### Blocking operational mode" in block
    assert "### Next three PRs" in block


def test_every_blocker_named_is_a_real_enum_value() -> None:
    """The doc may not invent a blocker, and may not keep a retired one."""
    named = {
        token for token in _BACKTICKED.findall(_status_block()) if token not in {"CI", "PR", "PRS"}
    }
    valid = {member.value for member in Blocker}

    assert named, "the status block names no blockers at all"
    assert named <= valid, f"not Blocker values: {sorted(named - valid)}"


def _tabled_blockers() -> set[str]:
    """Return the blockers the status table claims are blocking.

    Only table rows, not prose. The block also mentions `PROVENANCE_INCOMPLETE`
    to say it does *not* fire, and a check that could not tell those apart would
    force the doc to stop explaining itself.
    """
    rows = [line for line in _status_block().split("\n") if line.startswith("| `")]
    return {match for line in rows for match in _BACKTICKED.findall(line)}


def _firing_blockers() -> set[str]:
    """Return what the gate emits given live weather and a complete assessment."""
    return {
        blocker.value
        for blocker in operational_blockers(
            GateInputs(
                weather_is_live=True,
                weather_degraded=False,
                assessment_is_complete=True,
                provenance_is_complete=True,
                power_is_operational_grade=False,
            )
        )
    }


def test_every_firing_blocker_is_named_in_the_table() -> None:
    """A blocker the gate emits that the plan omits is a plan that understates."""
    missing = _firing_blockers() - _tabled_blockers()

    assert not missing, f"these fire but the plan does not name them: {sorted(missing)}"


def test_the_table_names_no_blocker_that_has_been_retired() -> None:
    """The other direction, and the one that rots quietly.

    Retiring a blocker in gate.py while the plan still lists it leaves the plan
    overstating what stands in the way -- which reads as diligence and is the
    same lie as understating.
    """
    stale = _tabled_blockers() - _firing_blockers()

    assert not stale, f"the plan names these but they no longer fire: {sorted(stale)}"


def test_the_plan_does_not_claim_operational_is_reachable() -> None:
    """The one sentence a reader must not come away with."""
    block = _status_block().lower()

    assert "unreachable today" in block
