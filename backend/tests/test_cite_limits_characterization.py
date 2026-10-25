"""Characterization tests for the ``cite_limits`` graph node.

These pin what the node returns today, for every path through it, so it can be
restructured without changing behavior. The node is called directly: it is a
plain ``state -> update`` function, and the update dict is what the graph
merges. Every test asserts on the returned dict, so a node that returned
nothing would fail every one of them.
"""

import logging
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.corpus import ingest_document
from suas.db.repository import get_aircraft
from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import CITED_FIELDS, make_cite_limits_node
from suas.rag.embedding import EmbeddingError, HashingEmbedder
from suas.schemas.domain import Aircraft
from tests.conftest import CALM_WEATHER, FakeReportService, FakeWeatherService
from tests.test_retrieval import _ASTRO, _entry

_AIRCRAFT_ID = "Freefly_Astro_Max"


class _FailingEmbedder:
    """Shares the hashing embedder's identity, so stored vectors are compared,
    then fails the way a remote embedding service does."""

    def __init__(self) -> None:
        self._inner = HashingEmbedder()

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        _ = texts
        raise EmbeddingError("embedding service unavailable")


def _deps(session_factory: async_sessionmaker[AsyncSession], embedder: Any) -> GraphDependencies:
    return GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),
        report=FakeReportService(),
        embedder=embedder,
    )


async def _aircraft(
    session_factory: async_sessionmaker[AsyncSession], **overrides: Any
) -> dict[str, Any]:
    async with session_factory() as session:
        aircraft = await get_aircraft(session, _AIRCRAFT_ID)
    assert aircraft is not None
    return Aircraft.model_validate({**aircraft.model_dump(), **overrides}).model_dump()


async def _ingest_astro(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await ingest_document(
            session,
            _entry(_ASTRO, _AIRCRAFT_ID, "a.txt"),
            _ASTRO,
            embedder=HashingEmbedder(),
        )


async def test_no_aircraft_means_citations_are_unavailable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    node = make_cite_limits_node(_deps(session_factory, HashingEmbedder()))
    assert await node({}) == {"citations": [], "citation_status": "unavailable"}


async def test_no_embedder_means_citations_are_unavailable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    node = make_cite_limits_node(_deps(session_factory, None))
    state = {"aircraft": await _aircraft(session_factory)}
    assert await node(state) == {"citations": [], "citation_status": "unavailable"}


async def test_an_empty_corpus_leaves_the_plan_unconfirmed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    node = make_cite_limits_node(_deps(session_factory, HashingEmbedder()))
    state = {"aircraft": await _aircraft(session_factory)}
    assert await node(state) == {"citations": [], "citation_status": "unconfirmed"}


async def test_matching_evidence_is_cited_per_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _ingest_astro(session_factory)
    node = make_cite_limits_node(_deps(session_factory, HashingEmbedder()))
    state = {"aircraft": await _aircraft(session_factory, pack_min_takeoff_c=10.0)}

    update = await node(state)

    assert update["citation_status"] == "confirmed"
    citations = update["citations"]
    assert citations
    assert all(set(c) == {"chunk_id", "field_path", "text", "page"} for c in citations)
    assert {c["field_path"] for c in citations} <= set(CITED_FIELDS)
    # Fields are asked about in CITED_FIELDS order, one hit at most each.
    order = [c["field_path"] for c in citations]
    assert order == [f for f in CITED_FIELDS if f in order]
    assert len(order) == len(set(order))
    pack = [c for c in citations if c["field_path"] == "pack_min_takeoff_c"]
    assert pack
    assert "10 C at" in pack[0]["text"]


async def test_a_field_the_aircraft_lacks_is_not_asked_about(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _ingest_astro(session_factory)
    node = make_cite_limits_node(_deps(session_factory, HashingEmbedder()))
    state = {"aircraft": await _aircraft(session_factory, pack_min_takeoff_c=None)}

    update = await node(state)

    assert "pack_min_takeoff_c" not in {c["field_path"] for c in update["citations"]}


async def test_a_retrieval_failure_is_unavailable_not_an_error(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _ingest_astro(session_factory)
    node = make_cite_limits_node(_deps(session_factory, _FailingEmbedder()))
    state = {"aircraft": await _aircraft(session_factory, pack_min_takeoff_c=10.0)}

    with caplog.at_level(logging.WARNING, logger="suas.graph.nodes"):
        update = await node(state)

    assert update == {"citations": [], "citation_status": "unavailable"}
    assert "Citation lookup failed, continuing unconfirmed" in caplog.text
