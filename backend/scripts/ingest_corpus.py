#!/usr/bin/env python3
"""Ingest the allowlisted corpus.

Offline on purpose. The API process never parses a document: ingest is a
deliberate act run against a checkout, with the manifest under review, so that
adding a source to the system leaves a commit behind.

Usage:
    python3 backend/scripts/ingest_corpus.py --corpus corpus
    python3 backend/scripts/ingest_corpus.py --corpus corpus --allow-eval-traps
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suas.config import get_settings
from suas.db.corpus import IngestSummary, ingest_document
from suas.db.engine import create_engine, create_session_factory
from suas.errors import SuasError
from suas.rag.manifest import load_manifest
from suas.rag.provider import build_embedder


async def ingest_all(corpus_root: Path, *, production: bool) -> list[IngestSummary]:
    """Ingest every document the manifest lists, returning one summary each."""
    entries = load_manifest(corpus_root / "manifest.json")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    client = httpx.AsyncClient()
    embedder = build_embedder(settings, client)

    summaries: list[IngestSummary] = []
    try:
        async with session_factory() as session:
            for path, entry in sorted(entries.items()):
                content = (corpus_root / path).read_bytes()
                summaries.append(
                    await ingest_document(
                        session,
                        entry,
                        content,
                        production=production,
                        embedder=embedder,
                    )
                )
    finally:
        await client.aclose()
        await engine.dispose()
    return summaries


def main() -> int:
    """Ingest the corpus and report what was stored and what was held back."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="corpus", help="corpus root directory")
    parser.add_argument(
        "--allow-eval-traps",
        action="store_true",
        help="permit kind=eval_trap documents; never use against a production database",
    )
    parsed = parser.parse_args()

    try:
        summaries = asyncio.run(
            ingest_all(Path(parsed.corpus), production=not parsed.allow_eval_traps)
        )
    except (SuasError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    total_quarantined = 0
    for summary in summaries:
        total_quarantined += summary.quarantined
        print(
            f"{summary.path}: {summary.chunks} chunks, "
            f"{summary.quarantined} quarantined "
            f"({summary.quarantine_rate:.1%})"
        )
        for pattern in sorted(set(summary.patterns)):
            print(f"    tripwire: {pattern!r}")

    if total_quarantined:
        print(
            f"\n{total_quarantined} chunk(s) quarantined. The configurations they "
            "belong to cannot run operational until a person clears them.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
