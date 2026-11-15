"""The operator can see why a model narrative was withheld."""

from typing import Any

import httpx
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.narrative import ungrounded_from_violations
from suas.graph.dependencies import GraphDependencies
from suas.graph.workflow import build_mission_graph
from suas.schemas.responses import UngroundedNumeric
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


def _wire(app: FastAPI, factory: async_sessionmaker[AsyncSession], report: Any) -> FastAPI:
    app.state.graph = build_mission_graph(
        GraphDependencies(
            session_factory=factory,
            weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
            report=report,
        ),
        InMemorySaver(),
    )
    return app


async def _plan_and_confirm(
    app: FastAPI,
) -> tuple[httpx.AsyncClient, dict[str, Any], dict[str, Any]]:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    created = (await client.post("/api/plan", json=_BODY)).json()
    signed = (
        await client.post(
            f"/api/plan/{created['thread_id']}/ack",
            json={
                "action": "confirm",
                "actor": "dispatcher-1",
                "inputs_hash": created["assessment"]["inputs_hash"],
            },
        )
    ).json()
    return client, created, signed


def test_a_single_unsupported_figure_is_split_into_value_and_unit() -> None:
    found = ungrounded_from_violations(["unsupported_numeric:225.7 wh"])
    assert found == [UngroundedNumeric(value="225.7", unit="Wh")]


def test_several_unsupported_figures_are_all_returned() -> None:
    found = ungrounded_from_violations(["unsupported_numeric:3 m/s", "unsupported_numeric:45 %"])
    assert found == [
        UngroundedNumeric(value="3", unit="m/s"),
        UngroundedNumeric(value="45", unit="%"),
    ]


async def test_a_grounded_model_brief_is_labelled_model(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _wire(app_with_graph, session_factory, FakeReportService("Review the limits."))
    client, _, signed = await _plan_and_confirm(app)
    await client.aclose()

    assert signed["report"] == "Review the limits."
    assert signed["narrative_source"] == "model"
    assert signed["report_source"] == "model"
    assert signed["ungrounded_numerics"] == []
    assert signed["narrative_reason"] == ""


async def test_one_invented_figure_is_exposed_on_the_plan_response(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app = _wire(app_with_graph, session_factory, FakeReportService("Hover power is 225.7 Wh."))
    client, _, signed = await _plan_and_confirm(app)

    assert signed["narrative_source"] == "deterministic"
    assert signed["report_source"] == "deterministic"
    assert signed["ungrounded_numerics"] == [{"value": "225.7", "unit": "Wh"}]
    assert signed["narrative_reason"] == "not found in the sealed result"
    assert "225.7" not in signed["report"]

    fetched = (await client.get(f"/api/plan/{signed['thread_id']}")).json()
    await client.aclose()
    assert fetched["found"] is True
    assert fetched["narrative_source"] == "deterministic"
    assert fetched["ungrounded_numerics"] == [{"value": "225.7", "unit": "Wh"}]
    assert fetched["narrative_reason"] == "not found in the sealed result"


async def test_several_invented_figures_are_all_listed(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    prose = "Wind is 99 m/s and humidity is 1 %."
    app = _wire(app_with_graph, session_factory, FakeReportService(prose))
    client, _, signed = await _plan_and_confirm(app)
    await client.aclose()

    figures = {(item["value"], item["unit"]) for item in signed["ungrounded_numerics"]}
    assert ("99", "m/s") in figures
    assert ("1", "%") in figures
    assert signed["narrative_source"] == "deterministic"
    assert signed["narrative_reason"] == "not found in the sealed result"


async def test_a_deterministic_brief_with_no_model_has_no_ungrounded_figures(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from suas.config import Settings
    from suas.services.llm import ReportService

    app = _wire(app_with_graph, session_factory, ReportService(Settings(openai_api_key="")))
    client, _, signed = await _plan_and_confirm(app)
    await client.aclose()

    assert signed["narrative_source"] == "deterministic"
    assert signed["ungrounded_numerics"] == []
    assert signed["narrative_reason"] == ""
    assert "model narrative unavailable" in signed["report"]
