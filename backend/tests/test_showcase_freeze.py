"""The showcase freeze after v0.4.0-eval is only oracle-bug fixes (#118)."""

from datetime import date
from pathlib import Path

import yaml

from tests.test_changelog import _CHANGELOG, _HEADING, _sections

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / ".github" / "ISSUE_TEMPLATE" / "attic.yml"
# Weeks whose Monday falls after the tag and before the freeze ends.
_FREEZE_WEEK_MONDAYS = frozenset({date(2026, 11, 16), date(2026, 11, 23)})


def test_the_attic_template_titles_new_ideas_for_after_the_freeze() -> None:
    assert _TEMPLATE.is_file(), "expected .github/ISSUE_TEMPLATE/attic.yml"
    loaded = yaml.safe_load(_TEMPLATE.read_text(encoding="utf-8"))
    assert str(loaded.get("title", "")).startswith("attic:")


def test_changelog_has_no_feature_prs_during_the_showcase_freeze() -> None:
    """A feature bullet in the freeze window would make the tag a moving target."""
    for heading, lines in _sections(_CHANGELOG.read_text(encoding="utf-8")):
        match = _HEADING.match(heading)
        assert match, heading
        monday = date.fromisoformat(match.group(1))
        if monday not in _FREEZE_WEEK_MONDAYS:
            continue
        for line in lines:
            lower = line.lower()
            # t59u and t60u are named, user-approved exceptions. Do not
            # generalize this escape to other work.
            allowed = (
                "oracle" in lower
                or ("t59u" in lower and "freeze exception" in lower and "hover" in lower)
                or (
                    "t60u" in lower
                    and "freeze exception" in lower
                    and ("ps-07" in lower or "#218" in lower or "#74" in lower)
                )
            )
            assert allowed, (
                f"{heading}: freeze-week entries may only record oracle-bug "
                f"fixes, or the t59u / t60u freeze exceptions, and must "
                f"say so: {line!r}"
            )
