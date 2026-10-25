"""Format rules for CHANGELOG.md (issue #80).

The changelog is one section per week, headed by that week's Monday, newest
first, with at most five one-line entries. Each entry names the PR or issue it
records, so every line can be traced to something that merged. Nothing here
requires a section for the current week: a week with no merges has no
section, and a dependency bump must not fail CI on a Monday.
"""

import re
from datetime import date
from pathlib import Path

import pytest

_CHANGELOG = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"
_HEADING = re.compile(r"^## Week of (\d{4}-\d{2}-\d{2})$")
_REFERENCE = re.compile(r"#\d+")
MAX_LINES_PER_WEEK = 5


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split the file into (heading, non-blank lines) from the first ``## ``."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line, []))
        elif sections and line.strip():
            sections[-1][1].append(line)
    return sections


@pytest.fixture(scope="module")
def sections() -> list[tuple[str, list[str]]]:
    assert _CHANGELOG.is_file(), "CHANGELOG.md is missing from the repository root"
    found = _sections(_CHANGELOG.read_text(encoding="utf-8"))
    assert found, "CHANGELOG.md has no weekly sections"
    return found


def test_every_heading_is_a_monday(sections: list[tuple[str, list[str]]]) -> None:
    for heading, _ in sections:
        match = _HEADING.match(heading)
        assert match, f"heading must read '## Week of YYYY-MM-DD': {heading!r}"
        monday = date.fromisoformat(match.group(1))
        assert monday.weekday() == 0, f"{heading!r} is not a Monday"


def test_weeks_are_newest_first_and_unique(sections: list[tuple[str, list[str]]]) -> None:
    weeks = [heading for heading, _ in sections]
    assert weeks == sorted(set(weeks), reverse=True)


def test_each_week_has_one_to_five_entries(sections: list[tuple[str, list[str]]]) -> None:
    for heading, lines in sections:
        assert 1 <= len(lines) <= MAX_LINES_PER_WEEK, (
            f"{heading!r} has {len(lines)} lines; the limit is {MAX_LINES_PER_WEEK}"
        )


def test_each_entry_is_one_bullet_naming_a_pr_or_issue(
    sections: list[tuple[str, list[str]]],
) -> None:
    for heading, lines in sections:
        for line in lines:
            assert line.startswith("- "), f"{heading!r}: not a one-line bullet: {line!r}"
            assert _REFERENCE.search(line), f"{heading!r}: names no PR or issue: {line!r}"


def test_the_parser_sees_what_a_reader_sees() -> None:
    text = "# Changelog\n\nIntro.\n\n## Week of 2026-10-19\n\n- a (#1)\n- b (#2)\n\n## Week of 2026-10-12\n- c (#3)\n"
    assert _sections(text) == [
        ("## Week of 2026-10-19", ["- a (#1)", "- b (#2)"]),
        ("## Week of 2026-10-12", ["- c (#3)"]),
    ]
