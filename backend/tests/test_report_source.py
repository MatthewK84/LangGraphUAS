"""`report_source`: whether a language model wrote the brief the operator reads.

The dashboard labels a model-written brief as one to check against the sealed
figures. Every deterministic path -- no key, a failed call, a brief withheld by
the seal, an abort, nothing written yet -- must say so, because a brief wrongly
labelled as calculator-only is trusted more than it has earned.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings
from suas.errors import ReportGenerationError
from suas.graph.dependencies import GraphDependencies
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


class _FailingReport:
    async def generate(self, **kwargs: Any) -> str:
        _ = kwargs
        raise ReportGenerationError("model unavailable")


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


async def _decide(app: FastAPI, action: str) -> tuple[dict[str, Any], dict[str, Any]]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/plan", json=_BODY)).json()
        decided = await client.post(
            f"/api/plan/{created['thread_id']}/ack",
            json={
                "action": action,
                "actor": "dispatcher-1",
                "inputs_hash": created["assessment"]["inputs_hash"],
            },
        )
    return created, decided.json()


async def test_prose_from_the_model_is_labelled_as_the_models(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    prose = FakeReportService("Review the limiting factors before launch.")
    _, signed = await _decide(_wire(app_with_graph, session_factory, prose), "confirm")

    assert signed["report"] == "Review the limiting factors before launch."
    assert signed["report_source"] == "model"


async def test_the_no_key_fallback_is_deterministic(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    keyless = ReportService(Settings(openai_api_key=""))
    _, signed = await _decide(_wire(app_with_graph, session_factory, keyless), "confirm")

    assert "model narrative unavailable" in signed["report"]
    assert signed["report_source"] == "deterministic"


async def test_a_failed_model_call_is_deterministic(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    failing = _FailingReport()
    _, signed = await _decide(_wire(app_with_graph, session_factory, failing), "confirm")

    assert "Narrative unavailable" in signed["report"]
    assert signed["report_source"] == "deterministic"


async def test_a_brief_the_seal_withheld_is_deterministic(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    invented = FakeReportService("Hover power is 98765 W.")
    _, signed = await _decide(_wire(app_with_graph, session_factory, invented), "confirm")

    assert "98765" not in signed["report"]
    assert signed["report_source"] == "deterministic"


async def test_an_abort_and_an_unsigned_plan_are_deterministic(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    prose = FakeReportService("Review the limiting factors before launch.")
    created, aborted = await _decide(_wire(app_with_graph, session_factory, prose), "abort")

    assert created["report"] == ""
    assert created["report_source"] == "deterministic"
    assert aborted["aborted"] is True
    assert aborted["report_source"] == "deterministic"
