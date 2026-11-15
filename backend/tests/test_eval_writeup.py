"""The eval writeup must stay honest: cited numbers, no clearance claim."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRITEUP = ROOT / "eval" / "WRITEUP.md"
README = ROOT / "README.md"
MIN_WORDS = 800
MAX_WORDS = 1500
# Title or body must not claim the pack is a clearance or a go-fly result.
FORBIDDEN = (
    "cleared for flight",
    "operational clearance",
    "safe to fly",
    "ready to fly",
    "flight-ready",
    "flight authorisation from this pack",
)


def _text() -> str:
    return WRITEUP.read_text(encoding="utf-8")


def _words(text: str) -> list[str]:
    return text.split()


def test_the_writeup_is_between_800_and_1500_words() -> None:
    count = len(_words(_text()))
    assert MIN_WORDS <= count <= MAX_WORDS, count


def test_the_title_does_not_imply_operational_clearance() -> None:
    title = _text().lstrip().splitlines()[0].lower()
    assert title.startswith("# ")
    for phrase in ("clearance", "operational eval", "ready for flight", "safe to fly"):
        assert phrase not in title, phrase


def test_the_body_makes_no_operational_claim() -> None:
    lower = _text().lower()
    for phrase in FORBIDDEN:
        assert phrase not in lower, phrase


def test_every_numbered_paragraph_cites_eval_results() -> None:
    """A figure without a results path is how invented numbers sneak in."""
    body = []
    for block in re.split(r"\n\s*\n", _text()):
        lines = [line for line in block.splitlines() if not line.startswith("#")]
        body.append("\n".join(lines).strip())
    missing = [
        para[:160]
        for para in body
        if para and re.search(r"\d", para) and "eval/results/" not in para
    ]
    assert missing == [], missing


def test_readme_links_the_writeup() -> None:
    text = README.read_text(encoding="utf-8")
    assert "eval/WRITEUP.md" in text
    opening = text.split("\n## Contents\n", 1)[0]
    assert "eval/WRITEUP.md" in opening
