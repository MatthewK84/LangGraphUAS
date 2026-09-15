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
    session.add(
        CorpusDocumentRow(
            document_id=document_id,
            path=entry.path,
            sha256=entry.sha256,
            source_url=entry.source_url,
            retrieved_at=entry.retrieved_at,
            kind=entry.kind,
            airframe_config_id=entry.airframe_config_id,
            ingested_at=datetime.now(UTC),
        )
    )

    summary = IngestSummary(path=entry.path, document_id=document_id)
    clean: list[ScreenResult] = []
    for paragraph in split_paragraphs(content.decode("utf-8", errors="replace")):
        result: ScreenResult = screen_chunk(paragraph)
        if result.is_clean:
            clean.append(result)
            continue

        summary.quarantined += 1
        summary.patterns.append(result.pattern)
        session.add(
            CorpusQuarantineRow(
                quarantine_id=str(uuid4()),
                document_path=entry.path,
                airframe_config_id=entry.airframe_config_id,
                pattern=result.pattern,
                text=result.text,
                quarantined_at=datetime.now(UTC),
            )
        )

    # Only screened chunks are embedded. A quarantined paragraph never becomes a
    # vector, so it cannot be retrieved even by accident.
    vectors: list[list[float]] = []
    if embedder is not None and clean:
        vectors = await embedder.embed([item.text for item in clean])

    for index, item in enumerate(clean):
        summary.chunks += 1
        session.add(
            CorpusChunkRow(
                chunk_id=str(uuid4()),
                document_id=document_id,
                airframe_config_id=entry.airframe_config_id,
                field_path=entry.field_path,
                page=None,
                text=item.text,
                embedding_json=json.dumps(vectors[index]) if vectors else None,
                embedding_model=embedder.model_id if (embedder and vectors) else None,
            )
        )

    await session.commit()
    if summary.quarantined:
        logger.warning(
            "Quarantined %d of %d chunks from %s: %s",
            summary.quarantined,
            summary.quarantined + summary.chunks,
            entry.path,
            sorted(set(summary.patterns)),
        )
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
