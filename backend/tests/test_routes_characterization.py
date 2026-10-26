"""Characterization tests for the acknowledge and replan routes.

These pin what ``POST /api/plan/{thread_id}/ack`` and ``POST /api/replan``
return today, through HTTP the way the dashboard calls them, so their internals
can be restructured without changing behavior. Each test asserts on values the
caller sees, so a route that returned nothing would fail every one of them.

The paths covered here are the ones the behavior tests in ``test_ack.py`` and
``test_replan.py`` leave open: a thread with checkpoints but no retention row,
a thread with no assessment, and the full shape of a successful response.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.observability import MetricsRegistry
from suas.api.routes import (
    _build_plan_response,
    _estimate_summary,
    _figure_provenance,
    _record_violations,
    _resume_payload,
)
from suas.db.retention import get_acknowledgement
from suas.reference_data import load_rows
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import AckRequest, MissionEdits
from tests.test_ack import _BODY
from tests.test_replan import _snapshot


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@dataclass
class _Snapshot:
    """The two attributes the routes read from a LangGraph state snapshot."""

    values: dict[str, Any]
    next: tuple[str, ...] = field(default_factory=tuple)


class _GraphWithState:
    """A graph whose only stored thread has the given values."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    async def aget_state(self, config: Any) -> _Snapshot:
        _ = config
        return _Snapshot(values=self._values)


async def _checkpoint_without_retention_row(graph: CompiledStateGraph, thread_id: str) -> None:
    """Run the graph to the review step without going through ``/api/plan``.

    That is the shape of a thread created before the retention table existed:
    checkpoints, but no row in ``mission_threads``.
    """
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke({**_BODY, "is_viable": True}, config=config, durability="sync")


# --- acknowledge -------------------------------------------------------------


async def test_a_confirmed_ack_returns_the_full_plan_response(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        thread_id = created["thread_id"]
        response = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={
                "action": "confirm",
                "actor": "dispatcher-1",
                "inputs_hash": created["assessment"]["inputs_hash"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == thread_id
    assert body["awaiting_ack"] is False
    assert body["aborted"] is False
    assert body["report"] == "TEST REPORT"
    assert body["assessment"] == created["assessment"]
    assert body["calculations"] == created["calculations"]
    assert body["weather"] == created["weather"]
    assert body["is_viable"] == (body["assessment"]["decision"] == "go")
    assert body["degraded"] is False
    assert body["warnings"] == []


async def test_an_ack_without_a_hash_is_accepted_and_recorded(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The hash check only applies when the caller sends one."""
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        thread_id = created["thread_id"]
        response = await client.post(
            f"/api/plan/{thread_id}/ack", json={"action": "confirm", "actor": "no-hash"}
        )

    assert response.status_code == 200
    async with session_factory() as session:
        row = await get_acknowledgement(session, thread_id)
    assert row is not None
    assert row.ack_actor == "no-hash"
    assert row.ack_inputs_hash == created["assessment"]["inputs_hash"]


async def test_an_abort_is_not_recorded_as_a_signature(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        thread_id = created["thread_id"]
        response = await client.post(
            f"/api/plan/{thread_id}/ack", json={"action": "abort", "actor": "dispatcher-1"}
        )

    assert response.status_code == 200
    assert response.json()["aborted"] is True
    async with session_factory() as session:
        row = await get_acknowledgement(session, thread_id)
    assert row is not None
    assert row.ack_actor is None


async def test_confirming_a_thread_with_no_retention_row_resumes_and_warns(
    app_with_graph: FastAPI,
    graph: CompiledStateGraph,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _checkpoint_without_retention_row(graph, "pre-retention")

    with caplog.at_level(logging.WARNING, logger="suas.api.routes"):
        async with _client(app_with_graph) as client:
            response = await client.post(
                "/api/plan/pre-retention/ack", json={"action": "confirm", "actor": "late"}
            )

    assert response.status_code == 200
    assert response.json()["report"] == "TEST REPORT"
    assert "Acknowledged thread pre-retention has no retention row" in caplog.text
    async with session_factory() as session:
        assert await get_acknowledgement(session, "pre-retention") is None


async def test_the_edit_payload_reaches_the_graph(app_with_graph: FastAPI) -> None:
    """An edit is resumed with exactly the fields the operator changed."""
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        thread_id = created["thread_id"]
        edited = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "edit", "actor": "d", "edits": {"hover_time_s": 900.0}},
        )
        state = (await client.get(f"/api/plan/{thread_id}")).json()

    assert edited.status_code == 200
    assert edited.json()["awaiting_ack"] is True
    assert state["awaiting_ack"] is True
    assert edited.json()["assessment"]["inputs_hash"] == state["assessment"]["inputs_hash"]


# --- replan ------------------------------------------------------------------


async def test_a_replan_returns_the_full_replan_response(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        thread_id = created["thread_id"]
        await client.post(
            f"/api/plan/{thread_id}/ack", json={"action": "confirm", "actor": "tester"}
        )
        briefed = (await client.get(f"/api/plan/{thread_id}")).json()
        response = await client.post("/api/replan", json=_snapshot(thread_id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "thread_id",
        "parent_thread_id",
        "severity",
        "recommended_action",
        "operational_ok",
        "live_energy",
        "briefed_margin_wh",
        "snapshot_age_s",
        "alerts",
    }
    assert body["thread_id"] == f"{thread_id}:1"
    assert body["parent_thread_id"] == thread_id
    assert body["briefed_margin_wh"] == briefed["calculations"]["battery_check"]["margin_wh"]
    assert body["live_energy"] is not None
    assert body["snapshot_age_s"] == round(body["snapshot_age_s"], 1)
    assert 0.0 <= body["snapshot_age_s"] < 60.0
    assert isinstance(body["operational_ok"], bool)
    assert isinstance(body["alerts"], list)


async def test_replanning_a_thread_with_no_retention_row_uses_the_first_child_id(
    app_with_graph: FastAPI,
    graph: CompiledStateGraph,
) -> None:
    await _checkpoint_without_retention_row(graph, "pre-retention")

    async with _client(app_with_graph) as client:
        first = await client.post("/api/replan", json=_snapshot("pre-retention"))
        second = await client.post("/api/replan", json=_snapshot("pre-retention"))

    assert first.status_code == 200
    assert first.json()["thread_id"] == "pre-retention:1"
    # With no row to count against, every replan lands on the same child id.
    assert second.json()["thread_id"] == "pre-retention:1"


async def test_replanning_a_thread_with_no_assessment_is_a_conflict(
    app_with_graph: FastAPI,
) -> None:
    app_with_graph.state.graph = _GraphWithState({"aircraft_id": "Skydio_X10D"})

    async with _client(app_with_graph) as client:
        response = await client.post("/api/replan", json=_snapshot("no-assessment"))

    assert response.status_code == 409
    assert response.json()["detail"] == "That thread has no assessment to replan against"


async def test_a_missing_battery_check_briefs_a_zero_margin(
    app_with_graph: FastAPI,
    graph: CompiledStateGraph,
) -> None:
    """The briefed margin defaults to zero rather than failing the replan."""
    async with _client(app_with_graph) as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
    stored = await graph.aget_state({"configurable": {"thread_id": created["thread_id"]}})
    values: dict[str, Any] = {**stored.values, "calculations": {}}
    app_with_graph.state.graph = _GraphWithState(values)

    async with _client(app_with_graph) as client:
        response = await client.post("/api/replan", json=_snapshot("no-battery-check"))

    assert response.status_code == 200
    assert response.json()["briefed_margin_wh"] == 0.0


# --- helpers and thread state --------------------------------------------------


class _GraphWithNoState:
    """A graph that has never seen the thread at all."""

    async def aget_state(self, config: Any) -> None:
        _ = config


async def test_a_thread_the_graph_has_never_seen_is_not_found(app_with_graph: FastAPI) -> None:
    app_with_graph.state.graph = _GraphWithNoState()

    async with _client(app_with_graph) as client:
        body = (await client.get("/api/plan/never-seen")).json()

    assert body["found"] is False
    assert body["awaiting_ack"] is False


async def test_a_thread_with_no_pending_step_is_found_and_not_awaiting(
    app_with_graph: FastAPI,
) -> None:
    """Missing values default to not viable, and an empty ``next`` means no ack is due."""
    app_with_graph.state.graph = _GraphWithState({"report": "Stored brief."})

    async with _client(app_with_graph) as client:
        body = (await client.get("/api/plan/finished")).json()

    assert body["found"] is True
    assert body["is_viable"] is False
    assert body["awaiting_ack"] is False
    assert body["report"] == "Stored brief."


def test_a_plan_response_from_empty_state_is_not_aborted_or_viable() -> None:
    response = _build_plan_response({}, "t-1")
    assert response.aborted is False
    assert response.is_viable is False
    assert response.awaiting_ack is False


def test_violations_are_counted_by_the_reason_before_the_colon() -> None:
    metrics = MetricsRegistry()
    _record_violations(metrics, ["contradiction:cleared for takeoff", ":no reason", "numeric"])
    exposition = metrics.render()
    assert "suas_llm_field_violations_total 3" in exposition
    assert 'reason="contradiction"} 1' in exposition
    assert 'reason="unknown"} 1' in exposition
    assert 'reason="numeric"} 1' in exposition


def test_an_estimate_summary_needs_both_a_median_and_a_count() -> None:
    assert _estimate_summary(None, 12, "high") is None
    assert _estimate_summary(820.0, None, "high") is None
    summary = _estimate_summary(820.0, 12, None)
    assert summary is not None
    assert summary.confidence == "low"


def test_the_resume_payload_carries_only_the_edits_given() -> None:
    request = AckRequest(action="edit", actor="pilot", edits=MissionEdits(hover_time_s=30.0))
    assert _resume_payload(request) == {
        "action": "edit",
        "actor": "pilot",
        "edits": {"hover_time_s": 30.0},
    }


async def test_a_plan_for_an_unknown_aircraft_answers_without_weather(
    app_with_graph: FastAPI,
) -> None:
    """Validation stops the graph before the weather fetch, and the route still answers.

    The plan metric treats an absent reading as not-a-fallback; it must not
    dereference the missing reading to decide that.
    """
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json={**_BODY, "aircraft_id": "NOPE"})

    assert response.status_code == 200
    body = response.json()
    assert body["weather"] is None
    assert body["is_viable"] is False
    assert (
        'suas_plan_outcomes_total{outcome="no_go",mode="advisory"} 1'
        in app_with_graph.state.metrics.render()
    )


@pytest.mark.parametrize("missing", ["calculations", "aircraft", "payload"])
def test_no_figure_provenance_without_calculations_aircraft_and_payload(missing: str) -> None:
    aircraft = Aircraft.model_validate(load_rows("aircraft.json")[0]).model_dump(mode="json")
    payload = Payload.model_validate(load_rows("payloads.json")[0]).model_dump(mode="json")
    values = {"calculations": {"hover_power_w": 1.0}, "aircraft": aircraft, "payload": payload}
    complete = _figure_provenance(values)
    del values[missing]
    assert complete
    assert _figure_provenance(values) == {}
