"""Citation checks, applied offline to the same rules the live path applies.

docs/rag-eval.md requires these run "in the live response assembler too, not
only in the eval". Where a live implementation exists, this module calls it
rather than restating it -- a second copy of a safety rule is a second thing to
keep in agreement, and the copy is the one that drifts.

``sealed_contamination`` and ``unsupported_numeric_rate`` therefore delegate to
``suas.graph.seal.unsupported_numerics``, which is what the report node runs.
"""

import unicodedata
from dataclasses import dataclass

from suas.graph.seal import unsupported_numerics


@dataclass(frozen=True)
class CitedSpan:
    """One quoted span in a brief, and the chunk it claims to come from."""

    chunk_id: str
    quote: str


def _normalise_whitespace(text: str) -> str:
    """Return text with unicode normalised and runs of whitespace collapsed.

    A quote that differs from its source only by a line break is the same quote.
    A quote that differs by a word is not, and that is the distinction this
    check exists to make.
    """
    return " ".join(unicodedata.normalize("NFKC", text).split())


def quote_verbatim(span: CitedSpan, chunk_text: str) -> bool:
    """Return whether the quoted span appears verbatim in the stored chunk.

    The highest-leverage check in the stack, and it is a substring compare. A
    model that paraphrases "do not launch below 10 C" into "avoid cold starts"
    has destroyed the evidence chain while still sounding correct, and this
    catches it for the cost of a string operation.
    """
    return _normalise_whitespace(span.quote) in _normalise_whitespace(chunk_text)


def citation_resolves(span: CitedSpan, chunks_by_id: dict[str, str]) -> bool:
    """Return whether the cited chunk exists at all."""
    return span.chunk_id in chunks_by_id


def citation_belongs_to_config(
    span: CitedSpan, config_by_chunk: dict[str, str], airframe_config_id: str
) -> bool:
    """Return whether the cited chunk belongs to the configuration being planned.

    Separate from ``citation_resolves`` because the failures differ: an id that
    does not exist is a hallucination, while an id belonging to another airframe
    is a filter that stopped working.
    """
    return config_by_chunk.get(span.chunk_id) == airframe_config_id


def url_allowlisted(url: str, document_urls: set[str]) -> bool:
    """Return whether a rendered URL came from the documents table.

    The model never emits a URL -- it cites a chunk_id and the assembler maps it
    at render time. Any URL not in this set came from somewhere it should not
    have, which in practice means it came out of chunk text.
    """
    return url in document_urls


def sealed_contamination(prose: str, supporting_text: str) -> list[str]:
    """Return unit-bearing numbers in prose that trace to nothing.

    Zero-tolerance in docs/rag-eval.md. Delegates to the live implementation, so
    the eval measures the control that actually runs rather than a restatement
    of it that can drift from it.
    """
    return unsupported_numerics(prose, supporting_text)


def unsupported_numeric_rate(briefs: list[tuple[str, str]]) -> float:
    """Return the fraction of briefs containing at least one untraceable number.

    A rate over briefs rather than over numbers: one brief with three invented
    figures is one bad brief, and weighting it triple would let a single
    pathological output dominate the corpus measurement.
    """
    if not briefs:
        return 0.0
    bad = sum(1 for prose, supporting in briefs if sealed_contamination(prose, supporting))
    return bad / len(briefs)
