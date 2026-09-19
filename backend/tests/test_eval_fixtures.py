"""The fixture file's own acceptance criteria, asserted rather than counted once.

docs/backlog/15 asks for 40+ rows, 6+ classes and 20% unanswerable. Those are
properties of a file that people will add rows to, so they belong in a test
rather than in a commit message.
"""

import json
from pathlib import Path
from typing import Any, Final

FIXTURES: Final[Path] = (
    Path(__file__).resolve().parent.parent.parent / "eval" / "rag_fixtures.jsonl"
)
REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "qid",
        "question",
        "airframe_config_id",
        "field_path",
        "relevant_chunk_ids",
        "hard_negatives",
        "expected_quote_contains",
        "answerable",
        "class",
    }
)


def _rows() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in FIXTURES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_there_are_at_least_forty_rows() -> None:
    assert len(_rows()) >= 40


def test_at_least_six_classes_are_represented() -> None:
    assert len({row["class"] for row in _rows()}) >= 6


def test_at_least_a_fifth_are_unanswerable() -> None:
    """The false-confirm gate is only meaningful if enough rows can trip it."""
    rows = _rows()
    unanswerable = sum(1 for row in rows if not row["answerable"])

    assert unanswerable / len(rows) >= 0.20


def test_every_row_carries_every_key() -> None:
    for row in _rows():
        assert set(row) == REQUIRED_KEYS, f"{row.get('qid')} has the wrong keys"


def test_question_ids_are_unique() -> None:
    ids = [row["qid"] for row in _rows()]

    assert len(ids) == len(set(ids))


def test_unanswerable_rows_claim_no_evidence() -> None:
    """A row that is both unanswerable and has relevant chunks is a contradiction."""
    for row in _rows():
        if not row["answerable"]:
            assert row["relevant_chunk_ids"] == []
            assert row["expected_quote_contains"] is None


def test_answerable_rows_name_evidence_and_a_quote() -> None:
    for row in _rows():
        if row["answerable"]:
            assert row["relevant_chunk_ids"], f"{row['qid']} claims answerable with no evidence"
            assert row["expected_quote_contains"]


def test_hard_negatives_never_overlap_the_positives() -> None:
    """A chunk cannot be both the answer and the trap for the same question."""
    for row in _rows():
        assert not set(row["hard_negatives"]) & set(row["relevant_chunk_ids"])


def test_the_safety_limit_classes_carry_hard_negatives() -> None:
    """Mandatory per docs/backlog/15: the Astro pack/airframe pair is the case."""
    pack_rows = [row for row in _rows() if row["class"] == "pack_takeoff_temperature"]

    assert pack_rows
    assert all(row["hard_negatives"] for row in pack_rows)
