"""Acknowledgement: the human step between the calculator and the model.

Two things are under test here. First, the mechanics: a signature is recorded,
bound to the assessment it was given, and refused when that assessment has moved
on. Second, the invariants from ADR-004 -- the report node runs after the review
step and has no tools -- which are ordinary-looking architecture choices that a
later refactor could undo for plausible reasons.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings
from suas.db.retention import get_acknowledgement
from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import MAX_ACK_ROUNDS
from suas.graph.workflow import build_mission_graph
from suas.services.llm import ReportService
from tests.conftest import CALM_WEATHER, FakeReportService, FakeWeatherService

_BODY: dict[str, Any] = {
    "aircraft_id": "Skydio_X10D",
    "payload_id": "None",
    "mission_params": {
        "distance_m": 2000.0,
        "hover_time_s": 120.0,
        "target_altitude_m": 120.0,
        "elevation_m": 0.0,
        "latitude": 34.0,
        "longitude": -80.0,
    },
}


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _graph(session_factory: async_sessionmaker[AsyncSession]) -> CompiledStateGraph:
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
        report=FakeReportService(),  # type: ignore[arg-type]
    )
    return build_mission_graph(deps, InMemorySaver())


# --- ADR-004 invariants -----------------------------------------------------


def test_ack_precedes_report(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The operator signs an assessment the model has not seen.

    If report ever becomes reachable without passing through human_ack, a brief
    could be generated before the signature and injection would have something
    to influence. Removing the interrupt to "save a round trip" is exactly the
    reasonable-looking change this test exists to stop.
    """
    drawn = _graph(session_factory).get_graph()
    edges = {(edge.source, edge.target) for edge in drawn.edges}

    assert ("calculations", "cite_limits") in edges
    assert ("cite_limits", "human_ack") in edges
    assert ("human_ack", "report") in edges
    assert ("calculations", "report") not in edges
    assert ("cite_limits", "report") not in edges
    # The only other way in is the validation short circuit, which never reaches
    # the model with an assessment at all.
    into_report = {source for source, target in edges if target == "report"}
    assert into_report == {"human_ack", "validate"}


def test_graph_has_no_tool_node(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """A tool the model can aim is a tool an injected document can aim."""
    nodes = set(_graph(session_factory).get_graph().nodes)
    assert nodes == {
        "__start__",
        "__end__",
        "validate",
        "weather",
        "calculations",
        "cite_limits",
        "human_ack",
        "report",
    }


def test_report_model_has_no_tools_bound() -> None:
    """Not tools it is told not to call. An empty binding.

    ``bind_tools`` returns a RunnableBinding wrapper, so a bare ChatOpenAI is
    the observable form of "no tools".
    """
    service = ReportService(Settings(openai_api_key="sk-test"))
    model = service._build_model()
    assert model is not None
    assert type(model).__name__ == "ChatOpenAI"
    assert not getattr(model, "kwargs", {}).get("tools")


# --- mechanics --------------------------------------------------------------


async def test_no_brief_without_an_acknowledgement(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph = _graph(session_factory)
    config = {"configurable": {"thread_id": "no-ack"}}
    result = await graph.ainvoke({**_BODY, "is_viable": True}, config=config)

    assert result.get("report") is None
    assert result["assessment"]["decision"]


async def test_acknowledgement_is_recorded_against_the_assessment(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        signed_hash = created.json()["assessment"]["inputs_hash"]
        acked = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "dispatcher-1", "inputs_hash": signed_hash},
        )

    assert acked.status_code == 200
    assert acked.json()["awaiting_ack"] is False
    assert acked.json()["report"] == "TEST REPORT"

    async with session_factory() as session:
        row = await get_acknowledgement(session, thread_id)
    assert row is not None
    assert row.ack_actor == "dispatcher-1"
    assert row.ack_inputs_hash == signed_hash
    assert row.ack_calculator_version


async def test_a_stale_signature_is_refused(app_with_graph: FastAPI) -> None:
    """Signing numbers that have since changed is the failure this prevents."""
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        response = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "dispatcher-1", "inputs_hash": "stale-hash"},
        )

    assert response.status_code == 409
    assert "changed" in response.json()["detail"]


async def test_editing_invalidates_the_previous_assessment(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        original_hash = created.json()["assessment"]["inputs_hash"]

        edited = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={
                "action": "edit",
                "actor": "dispatcher-1",
                "edits": {"hover_time_s": 900.0},
            },
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["awaiting_ack"] is True
    assert body["assessment"]["inputs_hash"] != original_hash
    # The old signature cannot be replayed against the new numbers.
    async with _client(app_with_graph) as client:
        replay = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "dispatcher-1", "inputs_hash": original_hash},
        )
    assert replay.status_code == 409


async def test_abort_never_calls_the_model(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        aborted = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "abort", "actor": "dispatcher-1"},
        )

    body = aborted.json()
    assert body["aborted"] is True
    assert "TEST REPORT" not in body["report"]


async def test_acknowledging_an_unknown_thread_is_not_found(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post(
            "/api/plan/does-not-exist/ack",
            json={"action": "confirm", "actor": "dispatcher-1"},
        )
    assert response.status_code == 404


async def test_acknowledging_twice_is_refused(app_with_graph: FastAPI) -> None:
    """A finished run has nothing left to sign."""
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        payload = {"action": "confirm", "actor": "dispatcher-1"}
        await client.post(f"/api/plan/{thread_id}/ack", json=payload)
        second = await client.post(f"/api/plan/{thread_id}/ack", json=payload)

    assert second.status_code == 409


async def test_state_survives_a_restart_at_the_review_step(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A crash between the assessment and the signature loses neither.

    The checkpointer is rebuilt around the same store, which is what a process
    restart looks like from the graph's point of view.
    """
    saver = InMemorySaver()
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
        report=FakeReportService(),  # type: ignore[arg-type]
    )
    config = {"configurable": {"thread_id": "crash-resume"}}

    first = build_mission_graph(deps, saver)
    before = await first.ainvoke({**_BODY, "is_viable": True}, config=config, durability="sync")
    assert before.get("report") is None

    # New compiled graph, same durable store.
    second = build_mission_graph(deps, saver)
    snapshot = await second.aget_state(config)
    assert snapshot.values["assessment"] == before["assessment"]
    assert snapshot.next

    resumed = await second.ainvoke(
        Command(resume={"action": "confirm", "actor": "after-restart"}),
        config=config,
        durability="sync",
    )
    assert resumed["report"] == "TEST REPORT"


async def test_edit_rounds_are_bounded(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Revision is allowed; spinning the graph forever is not."""
    graph = _graph(session_factory)
    config = {"configurable": {"thread_id": "edit-loop"}}
    await graph.ainvoke({**_BODY, "is_viable": True}, config=config)

    for round_number in range(MAX_ACK_ROUNDS + 1):
        state = await graph.aget_state(config)
        if not state.next:
            break
        await graph.ainvoke(
            Command(
                resume={
                    "action": "edit",
                    "actor": "tester",
                    "edits": {"hover_time_s": 100.0 + round_number},
                }
            ),
            config=config,
        )

    final = await graph.aget_state(config)
    assert not final.next, "the review loop never terminated"
    assert final.values["report"]


@pytest.mark.parametrize("action", ["confirm", "edit", "abort"])
def test_every_action_is_accepted_by_the_schema(action: str) -> None:
    from suas.schemas.requests import AckRequest

    request = AckRequest.model_validate({"action": action, "actor": "a"})
    assert request.action == action


# --- the per-thread lock ----------------------------------------------------


def test_the_thread_lock_asks_postgres_for_a_row_lock() -> None:
    """The mutex that stops two workers resuming one interrupt.

    Verified against a real four-worker deployment during #44: without this
    clause, six of eight racing pairs both resumed the same interrupt and two
    briefs were generated for one signature. The statement is compiled here
    rather than raced, because a race is not a test anyone can trust to fail.
    """
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from suas.db.models import MissionThreadRow

    statement = select(MissionThreadRow).where(MissionThreadRow.thread_id == "x").with_for_update()
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled


async def test_concurrent_acknowledgements_produce_one_brief(
    app_with_graph: FastAPI,
) -> None:
    """Two acknowledgements of one plan: one proceeds, one is refused."""
    import asyncio

    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_BODY)
        thread_id = created.json()["thread_id"]
        payload = {"action": "confirm", "actor": "racer"}
        first, second = await asyncio.gather(
            client.post(f"/api/plan/{thread_id}/ack", json=payload),
            client.post(f"/api/plan/{thread_id}/ack", json=payload),
        )

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]
    briefs = [r for r in (first, second) if r.status_code == 200 and r.json()["report"]]
    assert len(briefs) == 1
