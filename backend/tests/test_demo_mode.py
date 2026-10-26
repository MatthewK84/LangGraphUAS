"""Demo mode (#97): ``docker compose up`` with no keys, fixed weather, advisory only.

Demo mode swaps the live weather provider for one fixed reading tagged
``fixture``. The gate already refuses operational without operational-grade
weather, so the advisory-only rule needs no change to the gate.
"""

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph

from suas.config import DEMO_SESSION_KEY_SECRET, Settings
from suas.schemas.responses import WeatherReading, WeatherSource
from suas.services.weather import FixtureWeather, WeatherService, build_weather_service

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
_SECRET_NAME = re.compile(r"PASSWORD|KEY|SECRET|TOKEN")
_INTERPOLATION_ONLY = re.compile(r"\$\{[A-Z_]+(:-|:\?[^}]*)?\}")
_URL_PASSWORD = re.compile(r":([^:@/]*)@")

_OPERATIONAL_PLAN: dict[str, Any] = {
    "aircraft_id": "Skydio_X10D",
    "payload_id": "None",
    "assessment_mode": "operational",
    "mission_params": {
        "distance_m": 2000.0,
        "hover_time_s": 120.0,
        "target_altitude_m": 120.0,
        "elevation_m": 0.0,
        "latitude": 34.0,
        "longitude": -80.0,
    },
}


def _compose_environment() -> Iterator[tuple[str, str, str]]:
    services = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))["services"]
    for service, spec in services.items():
        for variable, value in (spec.get("environment") or {}).items():
            yield service, variable, str(value)


async def test_fixture_weather_is_labelled_and_never_operational_grade() -> None:
    reading = await FixtureWeather().fetch(34.0, -80.0)

    assert reading.source is WeatherSource.FIXTURE
    assert reading.is_operational_grade is False
    assert reading.fetched_at is None


async def test_demo_mode_wires_fixture_weather_and_only_demo_mode_does() -> None:
    async with httpx.AsyncClient() as client:
        assert isinstance(build_weather_service(Settings(demo_mode=True), client), FixtureWeather)
        assert isinstance(build_weather_service(Settings(demo_mode=False), client), WeatherService)


async def test_an_operational_request_in_demo_mode_comes_back_advisory(
    app_with_graph: FastAPI,
    build_graph: Callable[[WeatherReading], CompiledStateGraph],
) -> None:
    app_with_graph.state.graph = build_graph(await FixtureWeather().fetch(34.0, -80.0))
    transport = httpx.ASGITransport(app=app_with_graph)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/plan", json=_OPERATIONAL_PLAN)

    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["mode"] == "advisory"
    assert "WEATHER_NOT_LIVE" in assessment["blockers"]


# The one committed default: the public demo session secret (#82). It is not a
# credential anyone holds; the backend names it in a startup warning.
_DEMO_SESSION_DEFAULT = "${SESSION_KEY_SECRET:-" + DEMO_SESSION_KEY_SECRET + "}"


def test_compose_holds_no_secret_values() -> None:
    for service, variable, value in _compose_environment():
        for password in _URL_PASSWORD.findall(value):
            assert _INTERPOLATION_ONLY.fullmatch(password), f"{service}.{variable}"
        if _SECRET_NAME.search(variable) and value != _DEMO_SESSION_DEFAULT:
            assert _INTERPOLATION_ONLY.fullmatch(value), f"{service}.{variable} = {value!r}"


def test_compose_leaves_demo_mode_off_unless_asked() -> None:
    backend = {
        var: value for service, var, value in _compose_environment() if service == "backend"
    }
    assert backend["SUAS_DEMO_MODE"] == "${DEMO_MODE:-false}"
