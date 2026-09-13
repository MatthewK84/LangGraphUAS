"""Tests for the advisory / operational gate.

The property under test is that operational is granted by the backend and never
asserted by a caller, and that a gate condition this codebase cannot verify
counts against the plan rather than for it.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from suas.calculations.assessment import assess_mission, build_assessment
from suas.calculations.gate import GateInputs, operational_blockers, resolve_mode
from suas.schemas.assessment import AssessmentMode, Blocker, Decision
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams, MissionRequest
from suas.schemas.responses import WeatherReading, WeatherSource

_AIRCRAFT = Aircraft(
    id="TEST",
    name="Test Bird",
    weight_kg=6.0,
    max_payload_kg=2.7,
    battery_wh=588.0,
    max_wind_mps=12.0,
    cruise_speed_mps=15.0,
    hover_power_w=820.0,
    cruise_power_w=690.0,
    max_temp_c=50.0,
    min_temp_c=-20.0,
)
_PAYLOAD = Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0)
_PARAMS = MissionParams(
    distance_m=1000.0,
    hover_time_s=60.0,
    target_altitude_m=120.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_LIVE = WeatherReading(
    temperature_c=20.0,
    wind_speed_mps=3.0,
    wind_gust_mps=4.0,
    wind_direction=90.0,
    humidity_percent=40.0,
    conditions="calm",
    source=WeatherSource.LIVE,
)
_FALLBACK = _LIVE.model_copy(update={"source": WeatherSource.FALLBACK})

_ALL_CLEAR = GateInputs(
    weather_is_live=True,
    weather_degraded=False,
    assessment_is_complete=True,
)

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


def _assessment(weather: WeatherReading, requested: AssessmentMode):
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=weather
    )
    return build_assessment(
        calculations=calculations,
        inputs={"weather": weather.model_dump(mode="json")},
        requested_mode=requested,
        weather=weather,
    )


def test_requests_default_to_advisory() -> None:
    request = MissionRequest.model_validate(_BODY)
    assert request.assessment_mode is AssessmentMode.ADVISORY


def test_resolve_mode_grants_operational_only_with_no_blockers() -> None:
    assert resolve_mode(AssessmentMode.OPERATIONAL, []) is AssessmentMode.OPERATIONAL
    assert (
        resolve_mode(AssessmentMode.OPERATIONAL, [Blocker.WEATHER_NOT_LIVE])
        is AssessmentMode.ADVISORY
    )


def test_resolve_mode_never_upgrades_an_advisory_request() -> None:
    """Asking for advisory and getting operational would be a promotion nobody asked for."""
    assert resolve_mode(AssessmentMode.ADVISORY, []) is AssessmentMode.ADVISORY


def test_gate_fails_closed_on_unverifiable_conditions() -> None:
    """Even with everything we can check satisfied, unchecked conditions block.

    This is the test that changes when #38 lands: those blockers become real
    checks and stop appearing unconditionally.
    """
    blockers = operational_blockers(_ALL_CLEAR)
    assert Blocker.POWER_PROVENANCE_UNAVAILABLE in blockers
    assert Blocker.CITATIONS_UNAVAILABLE in blockers
    assert Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE in blockers
    assert Blocker.WEATHER_NOT_LIVE not in blockers


def test_fallback_weather_blocks_on_provenance_and_degradation() -> None:
    blockers = operational_blockers(
        GateInputs(weather_is_live=False, weather_degraded=True, assessment_is_complete=True)
    )
    assert Blocker.WEATHER_NOT_LIVE in blockers
    assert Blocker.WEATHER_DEGRADED in blockers


def test_incomplete_assessment_is_a_blocker() -> None:
    blockers = operational_blockers(
        GateInputs(weather_is_live=True, weather_degraded=False, assessment_is_complete=False)
    )
    assert Blocker.ASSESSMENT_INCOMPLETE in blockers


def test_operational_request_is_downgraded_not_refused() -> None:
    assessment = _assessment(_LIVE, AssessmentMode.OPERATIONAL)
    assert assessment.mode is AssessmentMode.ADVISORY
    assert assessment.is_operational is False
    assert assessment.blockers != []
    # The assessment still happened; the caller gets the result plus the reasons.
    assert assessment.decision is Decision.GO


def test_fallback_weather_names_its_blocker_on_the_assessment() -> None:
    assessment = _assessment(_FALLBACK, AssessmentMode.OPERATIONAL)
    assert Blocker.WEATHER_NOT_LIVE in assessment.blockers


async def test_plan_endpoint_honours_requested_mode(app_with_graph: FastAPI) -> None:
    body = {**_BODY, "assessment_mode": "operational"}
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["assessment"]["mode"] == "advisory"
    assert payload["assessment"]["blockers"] != []


async def test_plan_endpoint_rejects_an_unknown_mode(app_with_graph: FastAPI) -> None:
    body = {**_BODY, "assessment_mode": "definitely_operational"}
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["mode", "blockers", "assessment_mode", "requested_mode"])
def test_mode_fields_are_sealed(field: str) -> None:
    """A caller may ask for a mode. Nothing downstream may write one."""
    from suas.graph.seal import SEALED_FIELDS

    assert field in SEALED_FIELDS
