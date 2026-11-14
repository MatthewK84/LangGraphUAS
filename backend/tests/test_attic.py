"""The attic lists feeder repositories so they do not compete with this one.

The root README should point here, not sideways at earlier planners.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
ATTIC = ROOT / "attic" / "README.md"

FEEDERS = (
    "blue_uas_starter",
    "suas-llm-assistant",
)


def test_attic_readme_exists() -> None:
    assert ATTIC.is_file()


def test_each_feeder_is_named_with_what_it_contributed() -> None:
    text = ATTIC.read_text(encoding="utf-8")
    for name in FEEDERS:
        assert name in text, name
        assert f"https://github.com/MatthewK84/{name}" in text
    assert "contributed" in text.lower() or "fed" in text.lower() or "kept" in text.lower()


def test_the_root_readme_points_at_the_attic_not_sideways() -> None:
    assert "attic/README.md" in README
    assert "see my other planner" not in README.lower()
    for name in FEEDERS:
        assert f"github.com/MatthewK84/{name}" not in README
