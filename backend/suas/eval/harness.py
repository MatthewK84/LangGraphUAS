"""The retrieval evaluation, as a callable harness.

Lives in the package rather than in the script so the CI gate in
``tests/test_rag_gates.py`` and the reporting script measure with the same code.
Two implementations of one measurement is two numbers that can disagree, and the
disagreement is always discovered at the worst moment.
"""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.corpus import ingest_document
from suas.db.models import CorpusChunkRow
from suas.eval.retrieval_metrics import (
    DEFAULT_K,
    Fixture,
    RetrievedChunk,
    abstained,
    false_confirm,
    hard_negative_above_positive,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    wrong_config_leak,
)
from suas.eval.stats import wilson
from suas.rag.embedding import EmbeddingProvider, HashingEmbedder
from suas.rag.manifest import load_manifest
from suas.rag.retrieve import RRF_K, retrieve

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent.parent
CORPUS: Final[Path] = REPO_ROOT / "corpus" / "eval"
FIXTURES: Final[Path] = REPO_ROOT / "eval" / "rag_fixtures.jsonl"
BASELINE: Final[Path] = REPO_ROOT / "eval" / "baselines" / "retrieval.json"

# Classes where a wrong answer is a wrong limit on an aircraft, rather than a
# wrong number in a spec sheet. docs/backlog/16 holds these to a higher recall.
SAFETY_LIMIT_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "operating_temperature",
        "pack_takeoff_temperature",
        "max_wind",
        "takeoff_mass",
        "payload_capacity",
    }
)


@dataclass
class Totals:
    """Counts accumulated across fixtures, kept as integers for Wilson."""

    answerable: int = 0
    unanswerable: int = 0
    recall_hits: int = 0
    leaks: int = 0
    hard_negative_wins: int = 0
    false_confirms: int = 0
    abstentions: int = 0
    reciprocal_ranks: list[float] = field(default_factory=list)
    precisions: list[float] = field(default_factory=list)


def retriever_version(embedder_id: str) -> str:
    """Return a hash of everything that changes what retrieval returns.

    The report refuses to compare across versions. Comparing a recall number
    from one embedder against another's is not a regression test, it is two
    unrelated measurements plotted on one axis.
    """
    material = f"embedder={embedder_id};rrf_k={RRF_K};chunker=split_paragraphs;k={DEFAULT_K}"
    return sha256(material.encode()).hexdigest()[:16]


def load_fixtures() -> list[Fixture]:
    """Return every fixture, in file order."""
    rows: list[Fixture] = []
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data: dict[str, Any] = json.loads(line)
        rows.append(
            Fixture(
                qid=data["qid"],
                question=data["question"],
                airframe_config_id=data["airframe_config_id"],
                relevant_chunk_ids=data["relevant_chunk_ids"],
                hard_negatives=data["hard_negatives"],
                field_path=data["field_path"],
                answerable=data["answerable"],
                class_name=data["class"],
            )
        )
    return rows


def load_baseline() -> dict[str, Any]:
    """Return the committed baseline."""
    parsed: dict[str, Any] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return parsed


async def measure(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Ingest the eval corpus into the given database and run every fixture."""
    embedder = HashingEmbedder()
    entries = load_manifest(CORPUS / "manifest.json")
    async with session_factory() as session:
        for entry in entries.values():
            content = (CORPUS / entry.path).read_bytes()
            await ingest_document(session, entry, content, production=False, embedder=embedder)
        # The true owner of every chunk, read back from the database. Tagging a
        # retrieved chunk with the configuration that was *asked for* would make
        # wrong_config_leak vacuously zero -- it would measure the query, not
        # the filter.
        rows = await session.execute(
            select(CorpusChunkRow.chunk_id, CorpusChunkRow.airframe_config_id)
        )
        config_by_chunk: dict[str, str] = dict(rows.all())  # type: ignore[arg-type]

    fixtures = load_fixtures()
    totals = Totals()
    per_class: dict[str, dict[str, int]] = {}

    async with session_factory() as session:
        for fixture in fixtures:
            evidence = await retrieve(
                session,
                query=fixture.question,
                airframe_config_id=fixture.airframe_config_id,
                embedder=embedder,
                field_path=fixture.field_path,
            )
            retrieved = [
                RetrievedChunk(
                    chunk_id=item.chunk_id,
                    airframe_config_id=config_by_chunk.get(item.chunk_id, "UNKNOWN"),
                    field_path=item.field_path,
                )
                for item in evidence
            ]
            leaked = await _cross_config_leak(session, fixture, embedder, config_by_chunk)

            bucket = per_class.setdefault(fixture.class_name, {"n": 0, "recall": 0})
            bucket["n"] += 1

            if fixture.answerable:
                totals.answerable += 1
                hit = recall_at_k(retrieved, fixture)
                totals.recall_hits += int(hit)
                bucket["recall"] += int(hit)
                totals.reciprocal_ranks.append(reciprocal_rank(retrieved, fixture))
                totals.precisions.append(precision_at_k(retrieved, fixture))
                totals.abstentions += int(abstained(retrieved, fixture))
                totals.hard_negative_wins += int(hard_negative_above_positive(retrieved, fixture))
            else:
                totals.unanswerable += 1
                totals.false_confirms += int(false_confirm(retrieved, fixture))

            totals.leaks += int(leaked or wrong_config_leak(retrieved, fixture))

    return _report(totals, fixtures, per_class, embedder.model_id)


async def _cross_config_leak(
    session: AsyncSession,
    fixture: Fixture,
    embedder: EmbeddingProvider,
    config_by_chunk: dict[str, str],
) -> bool:
    """Return whether this question surfaces another airframe's chunks.

    Aims the same question at every other configuration. If a question about the
    Astro returns Astro content while filtered to the ANAFI, a WHERE clause is
    missing from a leg of the hybrid query -- which is the bug this whole metric
    exists to catch, and the one that reads as authoritative when it happens.
    """
    others = set(config_by_chunk.values()) - {fixture.airframe_config_id}
    for config in sorted(others):
        hits = await retrieve(
            session,
            query=fixture.question,
            airframe_config_id=config,
            embedder=embedder,
        )
        if any(config_by_chunk.get(item.chunk_id) != config for item in hits):
            return True
    return False


def _report(
    totals: Totals,
    fixtures: list[Fixture],
    per_class: dict[str, dict[str, int]],
    embedder_id: str,
) -> dict[str, Any]:
    """Assemble the report, with an interval on every rate."""
    recall = wilson(totals.recall_hits, totals.answerable)
    leak = wilson(totals.leaks, len(fixtures))
    hard = wilson(totals.hard_negative_wins, totals.answerable)
    confirm = wilson(totals.false_confirms, totals.unanswerable)
    abstain = wilson(totals.abstentions, totals.answerable)
    mrr = (
        sum(totals.reciprocal_ranks) / len(totals.reciprocal_ranks)
        if totals.reciprocal_ranks
        else 0.0
    )
    precision = sum(totals.precisions) / len(totals.precisions) if totals.precisions else 0.0
    return {
        "retriever_version": retriever_version(embedder_id),
        "embedder": embedder_id,
        "fixtures": len(fixtures),
        "answerable": totals.answerable,
        "unanswerable": totals.unanswerable,
        "gated": {
            "wrong_config_leak": _rate(leak),
            "hard_negative_above_positive": _rate(hard),
            "false_confirm_rate": _rate(confirm),
            "recall_at_4": _rate(recall),
            "mrr": round(mrr, 4),
        },
        "reported": {
            "precision_at_4": round(precision, 4),
            "abstain_rate": _rate(abstain),
            "field_path_purity": None,
        },
        "per_class_recall": {
            name: {"n": data["n"], "recall": data["recall"]}
            for name, data in sorted(per_class.items())
        },
        "notes": [
            "Measured with HashingEmbedder, a deterministic lexical projection, "
            "because CI cannot run sentence-transformers. recall_at_4 and mrr "
            "are therefore a REGRESSION FLOOR for retrieval logic, not a claim "
            "about retrieval quality. Re-measure once the embedding service is "
            "deployed, and do not compare across retriever_version.",
            "The corpus under corpus/eval/ is synthetic, written to resemble "
            "datasheet structure. Its figures are not a source of truth and "
            "must never be cited operationally.",
            "field_path_purity is null because no document in this corpus "
            "declares a field_path. Null is not zero and must not be averaged.",
            "hard_negative_above_positive is non-zero on one fixture, tm-05 "
            "('gross weight limit'), which ranks the payload paragraph above "
            "the gross-mass paragraph. Resolving it needs weight/mass synonymy, "
            "which a lexical projection cannot do and a real embedding model "
            "can. Recorded rather than removed: tuning the corpus until the "
            "metric reads zero measures the corpus, not the retriever.",
            "The _QUALIFIER stoplist in suas/rag/retrieve.py was chosen by "
            "reading which fixtures failed, so these fixtures are not a "
            "held-out measurement of that decision. The gates remain valid "
            "regression detectors; the absolute false_confirm figure should be "
            "re-earned against questions written after that change.",
        ],
    }


def _rate(interval: Any) -> dict[str, Any]:
    """Return a rate as a dict, so a reader cannot miss the interval."""
    return {
        "rate": round(interval.rate, 4),
        "ci95": [round(interval.low, 4), round(interval.high, 4)],
        "n": interval.n,
    }
