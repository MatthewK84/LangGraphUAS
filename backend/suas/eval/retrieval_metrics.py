"""Retrieval quality as pure functions over recorded outcomes.

Every function here takes what a retriever returned for one fixture and answers
one question about it. Nothing calls a database, a model, or the clock, so a
number in a report can be recomputed from the same inputs and come out the same.

The gate for each is in docs/rag-eval.md. Three of them are zero-tolerance, and
those three are the reason this module exists: they detect a WHERE clause going
missing from one leg of the hybrid query, which is the bug that survives code
review.
"""

from dataclasses import dataclass, field
from typing import Final

DEFAULT_K: Final[int] = 4


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk a retriever returned, with the identity needed to judge it."""

    chunk_id: str
    airframe_config_id: str
    field_path: str | None = None


@dataclass(frozen=True)
class Fixture:
    """One evaluation question and what a correct answer looks like."""

    qid: str
    question: str
    airframe_config_id: str
    relevant_chunk_ids: list[str]
    hard_negatives: list[str] = field(default_factory=list)
    field_path: str | None = None
    answerable: bool = True
    # "class" is a keyword, so the JSONL key is mapped on load.
    class_name: str = "unknown"


def recall_at_k(retrieved: list[RetrievedChunk], fixture: Fixture, k: int = DEFAULT_K) -> bool:
    """Return whether any relevant chunk appears in the top k.

    Binary per fixture rather than fractional, so the aggregate is a rate with a
    Wilson interval. With one or two relevant chunks per question, a fractional
    recall would mostly measure how many relevant chunks a question happens to
    have.
    """
    if not fixture.relevant_chunk_ids:
        return False
    top = {chunk.chunk_id for chunk in retrieved[:k]}
    return any(item in top for item in fixture.relevant_chunk_ids)


def reciprocal_rank(retrieved: list[RetrievedChunk], fixture: Fixture) -> float:
    """Return 1/rank of the first relevant chunk, or 0.0 if none was returned.

    Rank position is what matters: the model is shown four spans and must quote
    the right one. A relevant chunk at rank 4 is a worse outcome than the same
    chunk at rank 1, and recall@4 cannot tell them apart.
    """
    relevant = set(fixture.relevant_chunk_ids)
    for index, chunk in enumerate(retrieved, start=1):
        if chunk.chunk_id in relevant:
            return 1.0 / index
    return 0.0


def precision_at_k(retrieved: list[RetrievedChunk], fixture: Fixture, k: int = DEFAULT_K) -> float:
    """Return the fraction of the top k that is relevant. Reported, never gated.

    With k=4 and often a single relevant chunk, this caps near 0.25 and
    optimising it costs recall. It is here because a sudden move in it is worth
    looking at, not because a target exists.
    """
    if not retrieved:
        return 0.0
    top = retrieved[:k]
    relevant = set(fixture.relevant_chunk_ids)
    return sum(1 for chunk in top if chunk.chunk_id in relevant) / len(top)


def hard_negative_above_positive(retrieved: list[RetrievedChunk], fixture: Fixture) -> bool:
    """Return whether a hard negative outranks every relevant chunk.

    The Astro case this exists for: the -20 C airframe minimum and the 10 C pack
    takeoff minimum are different limits in adjacent paragraphs. Answering a
    pack question with the airframe paragraph reads as authoritative and is
    wrong in the direction that launches a cold battery.
    """
    if not fixture.hard_negatives or not fixture.relevant_chunk_ids:
        return False
    negatives = set(fixture.hard_negatives)
    positives = set(fixture.relevant_chunk_ids)
    for chunk in retrieved:
        if chunk.chunk_id in negatives:
            return True
        if chunk.chunk_id in positives:
            return False
    return False


def wrong_config_leak(retrieved: list[RetrievedChunk], fixture: Fixture) -> bool:
    """Return whether any chunk belongs to a different airframe configuration.

    Zero-tolerance. A non-zero rate means the structured filter went missing
    from a leg of the hybrid query, and the symptom is one airframe's limits
    presented as another's -- with a citation, which makes it look checked.
    """
    return any(chunk.airframe_config_id != fixture.airframe_config_id for chunk in retrieved)


def field_path_purity(retrieved: list[RetrievedChunk], fixture: Fixture) -> float | None:
    """Return the fraction of returned chunks matching the requested field_path.

    ``None`` when the fixture requests no field_path, which is not the same as
    zero and must not be averaged as if it were. On the current corpus no
    document declares a field_path, so this reports ``None`` for every row --
    see the note in the baseline.
    """
    if fixture.field_path is None:
        return None
    if not retrieved:
        return 0.0
    matching = sum(1 for chunk in retrieved if chunk.field_path == fixture.field_path)
    return matching / len(retrieved)


def false_confirm(retrieved: list[RetrievedChunk], fixture: Fixture) -> bool:
    """Return whether an unanswerable question produced confirming evidence.

    Zero-tolerance. The corpus does not establish the answer, so returning
    anything as though it does is a fabricated limit wearing a citation. An
    admitted gap is a worse user experience and a far better safety outcome.
    """
    return not fixture.answerable and bool(retrieved)


def abstained(retrieved: list[RetrievedChunk], fixture: Fixture) -> bool:
    """Return whether an answerable question returned nothing.

    Tracked, not gated at zero: abstaining is the correct response to a corpus
    that genuinely lacks the answer, and driving this to zero would mean
    rewarding a retriever for guessing.
    """
    return fixture.answerable and not retrieved
