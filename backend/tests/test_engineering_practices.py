"""The practices doc's Enforced half is checkable against ci.yml (#73).

A practices doc that overstates CI is worse than none, because a reviewer stops
checking. So every row of the Enforced in CI table names a job in
`.github/workflows/ci.yml` and the steps that hold it, and these tests read the
workflow to prove each one exists and can fail the run. Anything that cannot be
proven from the workflow file belongs under Aspirational or Reported.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PRACTICES = (ROOT / "docs" / "engineering-practices.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
CI: dict[str, Any] = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def _section(text: str, heading: str) -> str:
    start = text.index(f"\n{heading}\n") + len(heading) + 2
    depth = len(heading.split(" ", 1)[0])
    end = re.search(rf"^#{{1,{depth}}} ", text[start:], re.MULTILINE)
    return text[start : start + end.start() if end else len(text)]


def _enforced_rows() -> list[list[str]]:
    rows = _section(PRACTICES, "## Enforced in CI").splitlines()
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows if r.startswith("| ")]
    return [c for c in cells if c[0] != "Gate"]


def _blocking_steps(job: str) -> set[str]:
    steps = CI["jobs"][job]["steps"]
    return {s["name"] for s in steps if "name" in s and not s.get("continue-on-error")}


def test_the_doc_is_split_into_enforced_reported_and_aspirational() -> None:
    headings = re.findall(r"^## (.+)$", PRACTICES, re.MULTILINE)
    wanted = ["Enforced in CI", "Reported, not enforced", "Aspirational"]
    assert [h for h in headings if h in wanted] == wanted


def test_every_enforced_row_names_a_blocking_ci_job_and_its_steps() -> None:
    rows = _enforced_rows()
    assert len(rows) >= 10
    for gate, job_cell, step_cell, _rule in rows:
        jobs = re.findall(r"`([\w-]+)`", job_cell)
        assert len(jobs) == 1, gate
        job = jobs[0]
        assert job in CI["jobs"], gate
        assert not CI["jobs"][job].get("continue-on-error"), gate
        steps = re.findall(r'"([^"]+)"', step_cell)
        assert steps, gate
        assert set(steps) <= _blocking_steps(job), gate
        assert not any("report-only" in s for s in steps), gate


def test_every_blocking_ci_job_is_in_the_enforced_table() -> None:
    named = {re.findall(r"`([\w-]+)`", row[1])[0] for row in _enforced_rows()}
    report_only = {j for j, v in CI["jobs"].items() if "report-only" in v.get("name", "")}
    assert named == set(CI["jobs"]) - report_only
    assert report_only == {"mutation"}


def test_enforced_names_no_workflow_but_ci_yml() -> None:
    """Dependency auditing once read as a merge gate; the job had been removed."""
    enforced = _section(PRACTICES, "## Enforced in CI")
    assert set(re.findall(r"[\w-]+\.yml", enforced)) == {"ci.yml"}
    assert "pip-audit" not in enforced
    assert "audit.yml" in _section(PRACTICES, "## Reported, not enforced")


def test_test_files_named_as_gates_exist() -> None:
    enforced = _section(PRACTICES, "## Enforced in CI")
    named = set(re.findall(r"tests/(test_\w+\.py)", enforced))
    assert named
    assert [n for n in sorted(named) if not (ROOT / "backend" / "tests" / n).is_file()] == []


def test_readme_known_limitations_point_at_the_aspirational_list() -> None:
    limitations = _section(README, "### Known limitations")
    assert "docs/engineering-practices.md#aspirational" in limitations
    for unenforced in ("95%", "second reviewer", "SQLite", "required status checks"):
        assert unenforced in limitations, unenforced
