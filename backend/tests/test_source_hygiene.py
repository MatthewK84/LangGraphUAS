"""No source file may carry invisible or bidirectional control characters.

A bidi override in source makes a reviewer read different code from what the
interpreter runs ("Trojan Source", CVE-2021-42574). A pattern that has to
match those characters spells them as ``\\u`` escapes instead.
"""

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_SCANNED = (
    _REPO / "backend" / "suas",
    _REPO / "backend" / "tests",
    _REPO / "backend" / "scripts",
    _REPO / "backend" / "alembic",
    _REPO / "eval",
    _REPO / "frontend" / "src",
)
_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs"}
# Zero-width marks, bidi embeddings and overrides, word joiners, bidi isolates, BOM.
_HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


def _source_files() -> list[Path]:
    return sorted(
        path
        for root in _SCANNED
        for path in root.rglob("*")
        if path.suffix in _SUFFIXES and "node_modules" not in path.parts
    )


def test_the_scan_sees_the_backend() -> None:
    assert _REPO / "backend" / "suas" / "rag" / "screening.py" in _source_files()


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(_REPO)))
def test_no_hidden_characters_in_source(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        hidden = _HIDDEN.search(line)
        assert hidden is None, f"{path.name}:{number} has U+{ord(hidden.group(0)):04X}"
