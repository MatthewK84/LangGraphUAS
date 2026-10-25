"""Ingesting screened documents into the corpus.

The only write path into the corpus. Everything it stores has been named by the
manifest, verified against its recorded hash, normalised, and screened. Chunks
that trip the screener are written to quarantine instead of to the corpus, and
their presence blocks operational mode for the configuration they belong to
until a person clears them.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Final
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suas.db.models import CorpusChunkRow, CorpusDocumentRow, CorpusQuarantineRow
from suas.rag.embedding import EmbeddingProvider
from suas.rag.manifest import ManifestEntry, verify
from suas.rag.screening import ScreenResult, screen_chunk

logger: Final[logging.Logger] = logging.getLogger(__name__)

# Paragraphs shorter than this carry no useful statement on their own and are
# usually page furniture: headers, footers, stray figure numbers.
MIN_CHUNK_CHARS: Final[int] = 40


@dataclass
class IngestSummary:
    """What one document contributed, and what it cost."""

    path: str
    document_id: str
    chunks: int = 0
    quarantined: int = 0
    patterns: list[str] = field(default_factory=list)

    @property
    def quarantine_rate(self) -> float:
        """Return the fraction of chunks that tripped the screener."""
        total = self.chunks + self.quarantined
        return self.quarantined / total if total else 0.0


def split_paragraphs(text: str) -> list[str]:
    """Return the candidate chunks of a document, largest unit first.

    Paragraph splitting rather than fixed-size windows, so a chunk is a thing
    somebody wrote rather than an arbitrary slice of one.
    """
    parts = [part.strip() for part in text.split("\n\n")]
    return [part for part in parts if len(part) >= MIN_CHUNK_CHARS]


def chunk_identifier(document_path: str, ordinal: int) -> str:
    """Return a stable id for the nth surviving chunk of a document.

    Derived rather than random so that a chunk keeps its id across re-ingests.
    An evaluation fixture names the chunks it expects to be retrieved, and a
    fixture naming a uuid4 is a fixture that expires the next time anyone runs
    the ingest. The ordinal counts screened chunks, so quarantining a paragraph
    renumbers what follows it -- acceptable, because a corpus document changing
    is exactly when fixtures should be re-checked.
    """
    digest = sha256(f"{document_path}\x00{ordinal}".encode()).hexdigest()
    return f"c-{digest[:16]}"


def _document_row(entry: ManifestEntry, document_id: str) -> CorpusDocumentRow:
    """Return the record of where a verified document came from."""
    return CorpusDocumentRow(
        document_id=document_id,
        path=entry.path,
        sha256=entry.sha256,
        source_url=entry.source_url,
        retrieved_at=entry.retrieved_at,
        kind=entry.kind,
        airframe_config_id=entry.airframe_config_id,
        ingested_at=datetime.now(UTC),
    )


def _quarantine_row(entry: ManifestEntry, result: ScreenResult) -> CorpusQuarantineRow:
    """Return the quarantine record for a chunk that tripped the screener."""
    return CorpusQuarantineRow(
        quarantine_id=str(uuid4()),
        document_path=entry.path,
        airframe_config_id=entry.airframe_config_id,
        pattern=result.pattern,
        text=result.text,
        quarantined_at=datetime.now(UTC),
    )


def _screen_document(
    session: AsyncSession, entry: ManifestEntry, content: bytes, summary: IngestSummary
) -> list[ScreenResult]:
    """Screen every paragraph, quarantining the ones that trip, and return the clean ones."""
    clean: list[ScreenResult] = []
    for paragraph in split_paragraphs(content.decode("utf-8", errors="replace")):
        result: ScreenResult = screen_chunk(paragraph)
        if result.is_clean:
            clean.append(result)
            continue

        summary.quarantined += 1
        summary.patterns.append(result.pattern)
        session.add(_quarantine_row(entry, result))
    return clean


async def _embed_clean(
    embedder: EmbeddingProvider | None, clean: list[ScreenResult]
) -> list[list[float]]:
    """Return one vector per screened chunk, or none without an embedder or chunks.

    Only screened chunks are embedded. A quarantined paragraph never becomes a
    vector, so it cannot be retrieved even by accident.
    """
    if embedder is not None and clean:
        return await embedder.embed([item.text for item in clean])
    return []


def _add_chunks(
    session: AsyncSession,
    entry: ManifestEntry,
    document_id: str,
    clean: list[ScreenResult],
    vectors: list[list[float]],
    embedder: EmbeddingProvider | None,
    summary: IngestSummary,
) -> None:
    """Store the screened chunks, with their vectors when there are any."""
    for index, item in enumerate(clean):
        summary.chunks += 1
        session.add(
            CorpusChunkRow(
                chunk_id=chunk_identifier(entry.path, index),
                document_id=document_id,
                airframe_config_id=entry.airframe_config_id,
                field_path=entry.field_path,
                page=None,
                text=item.text,
                embedding_json=json.dumps(vectors[index]) if vectors else None,
                embedding_model=embedder.model_id if (embedder and vectors) else None,
            )
        )


def _log_quarantine(entry: ManifestEntry, summary: IngestSummary) -> None:
    """Warn when any chunk of a document was quarantined."""
    if summary.quarantined:
        logger.warning(
            "Quarantined %d of %d chunks from %s: %s",
            summary.quarantined,
            summary.quarantined + summary.chunks,
            entry.path,
            sorted(set(summary.patterns)),
        )


async def ingest_document(
    session: AsyncSession,
    entry: ManifestEntry,
    content: bytes,
    *,
    production: bool = True,
    embedder: EmbeddingProvider | None = None,
) -> IngestSummary:
    """Verify, screen, and store one document.

    Raises:
        ManifestError: when the bytes do not match the manifest, or the kind is
            one production must not ingest.
    """
    verify(entry, content, production=production)

    document_id: str = str(uuid4())
    session.add(_document_row(entry, document_id))

    summary = IngestSummary(path=entry.path, document_id=document_id)
    clean = _screen_document(session, entry, content, summary)
    vectors = await _embed_clean(embedder, clean)
    _add_chunks(session, entry, document_id, clean, vectors, embedder, summary)

    await session.commit()
    _log_quarantine(entry, summary)
    return summary


async def open_quarantine_configs(session: AsyncSession) -> set[str]:
    """Return every airframe configuration with an uncleared quarantine entry."""
    result = await session.execute(
        select(CorpusQuarantineRow.airframe_config_id).where(
            CorpusQuarantineRow.cleared_at.is_(None)
        )
    )
    return {value for value in result.scalars().all() if value}


async def has_open_quarantine(session: AsyncSession, airframe_config_id: str | None) -> bool:
    """Return whether this configuration has paperwork awaiting review."""
    if airframe_config_id is None:
        return False
    return airframe_config_id in await open_quarantine_configs(session)
