"""Finding the evidence for one field.

Retrieval answers "what does the manufacturer say about this number?" and
nothing else. It never decides anything; see ADR-003.

Three properties hold by construction rather than by care at the call site.

**The query is structured, never free text.** Candidates are selected by
``airframe_config_id`` and, when known, ``field_path``. The operator's mission
text is never embedded and matched against the whole corpus: that is the path by
which an injected document becomes the brief.

**Both legs carry the same filter.** Lexical and vector scores are computed over
one candidate set, so fusion cannot mix airframes. A retriever that returns the
Astro's pack limit for the ANAFI is worse than one that returns nothing, because
a plausible wrong limit is handed to a human as evidence.

**Vectors are only compared within one model.** Rows embedded by a different
model are excluded rather than scored, because a similarity between two models'
vectors is a number with no meaning.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suas.db.models import CorpusChunkRow, CorpusDocumentRow
from suas.rag.embedding import EmbeddingProvider, cosine_similarity

logger: Final[logging.Logger] = logging.getLogger(__name__)

# Reciprocal rank fusion. k=60 is the conventional starting point and is not
# tuned here: tuning it before there are recall numbers to tune against would be
# choosing a constant by feel.
RRF_K: Final[int] = 60

_WORD: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Evidence:
    """One retrieved chunk, with everything needed to cite it."""

    chunk_id: str
    text: str
    field_path: str | None
    page: int | None
    document_id: str
    source_url: str
    score: float


# Words that carry no evidence. A question is mostly these, and a chunk that
# matches only on them matches on nothing. Kept deliberately small and explicit:
# a long stoplist starts discarding real terms, and "maximum" or "minimum" would
# be exactly the wrong things to drop.
_FILLER: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "before",
        "can",
        "does",
        "do",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "many",
        "much",
        "must",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "did",
    }
)


def content_terms(text: str) -> set[str]:
    """Return the terms in text that could carry evidence."""
    return {term for term in _WORD.findall(text.lower()) if term not in _FILLER}


# Terms that say how a question is phrased rather than what it is about. Every
# limit in a datasheet is a "maximum" something, so matching on "maximum" alone
# matches every limit -- which is how "maximum operating altitude" came back with
# the wind limit as evidence. These still count toward ranking; they just cannot
# be the only reason a chunk is considered evidence at all.
_QUALIFIER: Final[frozenset[str]] = frozenset(
    {
        "maximum",
        "minimum",
        "max",
        "min",
        "highest",
        "lowest",
        "operating",
        "rate",
        "rated",
        "published",
        "limit",
        "limits",
        "total",
        "standard",
        "aircraft",
        "airframe",
        "this",
        "handle",
        "hold",
    }
)


def subject_terms(text: str) -> set[str]:
    """Return the terms that say what a question or chunk is about."""
    return content_terms(text) - _QUALIFIER


def _shares_content(query: str, text: str) -> bool:
    """Return whether a chunk shares a subject term with the query.

    The floor that lets retrieval abstain. Without it, fusion always returns
    top_k: the vector leg scores every chunk non-zero, so a question the corpus
    cannot answer comes back with evidence anyway -- a fabricated limit wearing a
    citation, which is worse than an admitted gap.

    A caveat that belongs with the number rather than buried: ``_QUALIFIER`` was
    chosen by reading which fixtures failed, so eval/rag_fixtures.jsonl is not a
    held-out measurement of *this* decision. It remains a valid regression
    detector -- the zero-tolerance gates catch a filter that stops working
    whether or not the stoplist was tuned -- but the absolute false_confirm
    figure should be re-earned against questions written after this change.
    """
    query_subjects = subject_terms(query)
    if not query_subjects:
        # Nothing but qualifiers. Fall back to any content term rather than
        # refusing outright, so a terse question is answered rather than dropped.
        return bool(content_terms(query) & content_terms(text))
    return bool(query_subjects & subject_terms(text))


def _lexical_score(query: str, text: str) -> float:
    """Return the fraction of query terms present in the text.

    Deliberately simple. It is one of two legs, and its job is to catch the exact
    tokens a vector model smears: model numbers, cell counts, units.
    """
    terms = set(_WORD.findall(query.lower()))
    if not terms:
        return 0.0
    body = set(_WORD.findall(text.lower()))
    return len(terms & body) / len(terms)


def _rank_map(scored: list[tuple[str, float]]) -> dict[str, int]:
    """Return chunk id to 1-based rank, best first, ignoring zero scores."""
    ordered = sorted((item for item in scored if item[1] > 0.0), key=lambda i: -i[1])
    return {chunk_id: position for position, (chunk_id, _) in enumerate(ordered, start=1)}


def fuse(lexical: list[tuple[str, float]], vector: list[tuple[str, float]]) -> list[str]:
    """Return chunk ids ordered by reciprocal rank fusion of the two legs.

    Scores are fused by rank rather than by value because the two legs are not
    on the same scale, and adding a cosine to a term-overlap fraction produces a
    number that means nothing.
    """
    lexical_ranks = _rank_map(lexical)
    vector_ranks = _rank_map(vector)
    fused: dict[str, float] = {}
    for chunk_id in set(lexical_ranks) | set(vector_ranks):
        score = 0.0
        if chunk_id in lexical_ranks:
            score += 1.0 / (RRF_K + lexical_ranks[chunk_id])
        if chunk_id in vector_ranks:
            score += 1.0 / (RRF_K + vector_ranks[chunk_id])
        fused[chunk_id] = score
    return [chunk_id for chunk_id, _ in sorted(fused.items(), key=lambda i: -i[1])]


async def retrieve(
    session: AsyncSession,
    *,
    query: str,
    airframe_config_id: str,
    embedder: EmbeddingProvider,
    field_path: str | None = None,
    candidates: int = 20,
    top_k: int = 4,
) -> list[Evidence]:
    """Return the best evidence for one field of one configuration.

    Returns an empty list rather than widening the search when nothing matches.
    An unconfirmed citation is a supported outcome; a citation from the wrong
    aircraft is not.
    """
    statement = (
        select(CorpusChunkRow, CorpusDocumentRow)
        .join(CorpusDocumentRow, CorpusChunkRow.document_id == CorpusDocumentRow.document_id)
        .where(CorpusChunkRow.airframe_config_id == airframe_config_id)
        .limit(candidates * 5)
    )
    if field_path is not None:
        statement = statement.where(CorpusChunkRow.field_path == field_path)

    rows = list((await session.execute(statement)).all())
    # Applied before scoring, not after: a chunk sharing no substantive term
    # with the question is not a weak match to be ranked low, it is not evidence.
    rows = [pair for pair in rows if _shares_content(query, pair[0].text)]
    if not rows:
        return []

    lexical: list[tuple[str, float]] = [
        (chunk.chunk_id, _lexical_score(query, chunk.text)) for chunk, _ in rows
    ]

    vector: list[tuple[str, float]] = []
    comparable = [
        (chunk, document)
        for chunk, document in rows
        if chunk.embedding_json and chunk.embedding_model == embedder.model_id
    ]
    skipped = sum(1 for chunk, _ in rows if chunk.embedding_model not in (None, embedder.model_id))
    if skipped:
        logger.warning(
            "Skipped %d chunk(s) embedded by a different model than %s",
            skipped,
            embedder.model_id,
        )
    if comparable:
        query_vector = (await embedder.embed([query]))[0]
        vector = [
            (chunk.chunk_id, cosine_similarity(query_vector, json.loads(chunk.embedding_json)))
            for chunk, _ in comparable
            if chunk.embedding_json
        ]

    by_id = {chunk.chunk_id: (chunk, document) for chunk, document in rows}
    ordered = fuse(lexical, vector)[:top_k]
    results: list[Evidence] = []
    for position, chunk_id in enumerate(ordered, start=1):
        chunk, document = by_id[chunk_id]
        results.append(
            Evidence(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                field_path=chunk.field_path,
                page=chunk.page,
                document_id=document.document_id,
                source_url=document.source_url,
                score=1.0 / position,
            )
        )
    return results
