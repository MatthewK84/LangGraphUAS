"""Every plan log line carries the four fields that tie it to a run (#110).

A log line from a plan could not be tied to the calculator that produced it,
the weather it used, or the mode the gate granted, and the access line for the
request was written after its request id had been cleared. These tests write a
fixture log through the production filter and formatters, then pick out one
request's lines the way an operator would: one grep for its request id.
"""

import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.calculations.assessment import CALCULATOR_VERSION
from suas.graph.dependencies import GraphDependencies
from suas.graph.workflow import build_mission_graph
from suas.logging_config import TRACE_FIELDS, JsonFormatter, RequestIdFilter, text_formatter
from suas.services.llm import ReportGenerationError
from tests.conftest import CALM_WEATHER, FakeReportService, FakeWeatherService
from tests.test_ack import _BODY

_FIELDS = ("request_id", *TRACE_FIELDS)
_LogFile = Callable[[logging.Formatter], Path]


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[_LogFile]:
    """Route root logging at INFO into a file through the production filter."""
    root = logging.getLogger()
    handlers: list[logging.Handler] = []
    level = root.level

    def _attach(formatter: logging.Formatter) -> Path:
        path = tmp_path / "plan.log"
        handler = logging.FileHandler(path)
        handler.addFilter(RequestIdFilter())
        handler.setFormatter(formatter)
        root.addHandler(handler)
        handlers.append(handler)
        root.setLevel(logging.INFO)
        return path

    yield _attach
    for handler in handlers:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)


def _grep(path: Path, request_id: str) -> list[dict[str, Any]]:
    """The one grep: every JSON line for a request id."""
    needle = f'"request_id": "{request_id}"'
    return [json.loads(line) for line in path.read_text().splitlines() if needle in line]


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class _RaisingWeather:
    async def fetch(self, latitude: float, longitude: float) -> Any:
        _ = (latitude, longitude)
        raise RuntimeError("provider exploded")


class _FailingReport:
    async def generate(self, **kwargs: Any) -> str:
        _ = kwargs
        raise ReportGenerationError("model unavailable")


def _wire(app: FastAPI, factory: async_sessionmaker[AsyncSession], **deps: Any) -> FastAPI:
    wired = {"weather": FakeWeatherService(CALM_WEATHER), "report": FakeReportService(), **deps}
    app.state.graph = build_mission_graph(
        GraphDependencies(session_factory=factory, **wired),  # type: ignore[arg-type]
        InMemorySaver(),
    )
    return app


async def test_the_plan_access_line_carries_all_four_fields(
    app_with_graph: FastAPI, log_file: _LogFile
) -> None:
    path = log_file(JsonFormatter())
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=_BODY, headers={"X-Request-ID": "rid-ok"})

    assert response.status_code == 200
    [line] = [entry for entry in _grep(path, "rid-ok") if "POST /api/plan" in entry["message"]]
    assert line["calculator_version"] == CALCULATOR_VERSION
    assert line["weather_source"] == "live"
    assert line["assessment_mode"] == response.json()["assessment"]["mode"]


async def test_the_text_format_carries_them_as_greppable_pairs(
    app_with_graph: FastAPI, log_file: _LogFile
) -> None:
    path = log_file(text_formatter())
    async with _client(app_with_graph) as client:
        await client.post("/api/plan", json=_BODY, headers={"X-Request-ID": "rid-text"})

    [line] = [row for row in path.read_text().splitlines() if "POST /api/plan" in row]
    assert "[rid-text]" in line
    assert f"calculator_version={CALCULATOR_VERSION}" in line
    assert "weather_source=live" in line
    assert "assessment_mode=advisory" in line


async def test_an_unhandled_failure_keeps_the_request_id_and_version(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    log_file: _LogFile,
) -> None:
    """The 500 line is written outside the middleware; it must still be tied."""
    app = _wire(app_with_graph, session_factory, weather=_RaisingWeather())
    path = log_file(JsonFormatter())
    async with _client(app) as client:
        response = await client.post("/api/plan", json=_BODY, headers={"X-Request-ID": "rid-500"})

    assert response.status_code == 500
    [line] = [entry for entry in _grep(path, "rid-500") if "Unhandled error" in entry["message"]]
    assert set(_FIELDS) <= line.keys()
    assert line["calculator_version"] == CALCULATOR_VERSION
    assert line["weather_source"] == "-"


async def test_a_line_from_the_ack_run_carries_the_signed_runs_fields(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    log_file: _LogFile,
) -> None:
    """The report fallback logs during the ack, after the nodes that set the fields."""
    app = _wire(app_with_graph, session_factory, report=_FailingReport())
    path = log_file(JsonFormatter())
    async with _client(app) as client:
        created = await client.post("/api/plan", json=_BODY)
        acked = await client.post(
            f"/api/plan/{created.json()['thread_id']}/ack",
            json={
                "action": "confirm",
                "actor": "dispatcher-1",
                "inputs_hash": created.json()["assessment"]["inputs_hash"],
            },
            headers={"X-Request-ID": "rid-ack"},
        )

    assert acked.status_code == 200
    [line] = [entry for entry in _grep(path, "rid-ack") if "Falling back" in entry["message"]]
    assert line["calculator_version"] == CALCULATOR_VERSION
    assert line["weather_source"] == "live"
    assert line["assessment_mode"] == "advisory"


async def test_fields_do_not_outlive_a_successful_request(
    app_with_graph: FastAPI, log_file: _LogFile
) -> None:
    path = log_file(JsonFormatter())
    async with _client(app_with_graph) as client:
        await client.post("/api/plan", json=_BODY, headers={"X-Request-ID": "rid-done"})
    logging.getLogger("suas.test").info("after the request")

    after = json.loads(path.read_text().splitlines()[-1])
    assert after["message"] == "after the request"
    assert {name: after[name] for name in _FIELDS} == dict.fromkeys(_FIELDS, "-")
