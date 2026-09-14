"""Replanning against live telemetry.

The acceptance case is the first test: brief a plan, report having burned more
energy than expected, and get ENERGY_BELOW_RESERVE carrying both number sets.
The rest pin the properties that make that answer trustworthy -- the briefed
assessment does not move, no model is involved, and an alert of any kind means
the replan is advice rather than clearance.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from suas.calculations.replan import (
    MAX_OPERATIONAL_SNAPSHOT_AGE_S,
    compute_live_energy,
    evaluate_replan,
)
from suas.schemas.alerts import AlertCode, RecommendedAction, Severity
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.telemetry import TelemetrySnapshot

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
_PAYLOAD = Payload(id="None", name="None", weight_kg=0.0, power_draw_w=0.0)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _snapshot(thread_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "thread_id": thread_id,
        "ts": datetime.now(UTC).isoformat(),
        "latitude": 34.0,
        "longitude": -80.0,
        "alt_m": 100.0,
        "soc_fraction": 0.5,
        "remaining_leg_m": 1000.0,
        "remaining_hover_s": 30.0,
        "oat_c": 18.0,
        "wind_mps": 3.0,
        "payload_attached": False,
    }
    body.update(overrides)
    return body


async def _brief(client: httpx.AsyncClient) -> str:
    created = await client.post("/api/plan", json=_BODY)
    thread_id: str = created.json()["thread_id"]
    await client.post(f"/api/plan/{thread_id}/ack", json={"action": "confirm", "actor": "tester"})
    return thread_id


# --- the acceptance case ----------------------------------------------------


async def test_a_snapshot_that_burned_too_much_raises_energy_below_reserve(
    app_with_graph: FastAPI,
) -> None:
    async with _client(app_with_graph) as client:
        thread_id = await _brief(client)
        response = await client.post(
            "/api/replan",
            json=_snapshot(thread_id, soc_fraction=0.04, remaining_leg_m=4000.0),
        )

    assert response.status_code == 200
    body = response.json()
    codes = [alert["code"] for alert in body["alerts"]]
    assert AlertCode.ENERGY_BELOW_RESERVE.value in codes

    energy = next(a for a in body["alerts"] if a["code"] == AlertCode.ENERGY_BELOW_RESERVE.value)
    # Both number sets, so the recommendation can be checked rather than trusted.
    assert "margin_wh" in energy["briefed"]
    assert {"available_wh", "required_wh", "residual_wh", "reserve_wh"} <= set(energy["live"])
    assert "residual_wh" in energy["delta"]
    assert body["severity"] == Severity.ABORT.value
    assert body["recommended_action"] == RecommendedAction.LAND_NOW.value


# --- the briefed plan does not move -----------------------------------------


async def test_replanning_leaves_the_briefed_thread_untouched(
    app_with_graph: FastAPI,
) -> None:
    """The signed assessment is evidence. A replan reads it and writes nothing."""
    async with _client(app_with_graph) as client:
        thread_id = await _brief(client)
        before = (await client.get(f"/api/plan/{thread_id}")).json()

        replan = await client.post("/api/replan", json=_snapshot(thread_id, soc_fraction=0.05))
        after = (await client.get(f"/api/plan/{thread_id}")).json()

    assert before == after
    assert replan.json()["thread_id"] == f"{thread_id}:1"
    assert replan.json()["parent_thread_id"] == thread_id


async def test_each_replan_gets_its_own_child_thread(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        thread_id = await _brief(client)
        first = await client.post("/api/replan", json=_snapshot(thread_id))
        second = await client.post("/api/replan", json=_snapshot(thread_id))

    assert first.json()["thread_id"] == f"{thread_id}:1"
    assert second.json()["thread_id"] == f"{thread_id}:2"


async def test_replanning_an_unknown_thread_is_not_found(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post("/api/replan", json=_snapshot("no-such-thread"))
    assert response.status_code == 404


# --- no model, ever ---------------------------------------------------------


def test_the_replan_graph_has_no_model_node() -> None:
    """A replan runs while an aircraft is airborne. Nothing waits on a model."""
    from langgraph.checkpoint.memory import InMemorySaver

    from suas.graph.replan import ReplanDependencies, build_replan_graph

    nodes = set(build_replan_graph(ReplanDependencies(), InMemorySaver()).get_graph().nodes)
    assert nodes == {
        "__start__",
        "__end__",
        "ingest_telemetry",
        "merge_briefed_state",
        "recalculate",
        "compare",
        "alert",
    }


async def test_a_replan_returns_no_brief(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        thread_id = await _brief(client)
        response = await client.post("/api/replan", json=_snapshot(thread_id))
    assert "report" not in response.json()


# --- the individual rules ---------------------------------------------------


def test_wind_beyond_the_airframe_limit_aborts() -> None:
    snapshot = TelemetrySnapshot.model_validate(_snapshot("t", wind_mps=25.0))
    _, alerts = evaluate_replan(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=snapshot,
        briefed_margin_wh=100.0,
        reserve_percent=20.0,
        age_s=1.0,
    )
    wind = next(a for a in alerts if a.code is AlertCode.WIND_EXCEEDS_LIMIT)
    assert wind.severity is Severity.ABORT
    assert wind.live["wind_mps"] == 25.0


def test_a_stale_snapshot_cannot_carry_operational_weight(app_with_graph: FastAPI) -> None:
    snapshot = TelemetrySnapshot.model_validate(_snapshot("t"))
    _, alerts = evaluate_replan(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=snapshot,
        briefed_margin_wh=100.0,
        reserve_percent=20.0,
        age_s=MAX_OPERATIONAL_SNAPSHOT_AGE_S + 1.0,
    )
    stale = next(a for a in alerts if a.code is AlertCode.SOC_STALE)
    assert stale.severity is Severity.WATCH
    assert stale.recommended_action is RecommendedAction.ADVISORY_ONLY


def test_a_snapshot_from_the_future_is_not_negatively_aged() -> None:
    future = datetime.now(UTC) + timedelta(seconds=120)
    snapshot = TelemetrySnapshot.model_validate(_snapshot("t", ts=future.isoformat()))
    assert snapshot.age_s(datetime.now(UTC)) == 0.0


def test_missing_wind_is_a_watch_not_a_pass() -> None:
    """Not being able to check a limit is not the same as clearing it."""
    body = _snapshot("t")
    body.pop("wind_mps")
    snapshot = TelemetrySnapshot.model_validate(body)
    _, alerts = evaluate_replan(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=snapshot,
        briefed_margin_wh=100.0,
        reserve_percent=20.0,
        age_s=1.0,
    )
    assert any(a.code is AlertCode.WEATHER_DEGRADED for a in alerts)


def test_cold_reduces_available_energy() -> None:
    warm = compute_live_energy(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=TelemetrySnapshot.model_validate(_snapshot("t", oat_c=20.0)),
        reserve_percent=20.0,
    )
    cold = compute_live_energy(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=TelemetrySnapshot.model_validate(_snapshot("t", oat_c=-10.0)),
        reserve_percent=20.0,
    )
    assert cold.available_wh < warm.available_wh
    # The reserve is measured against the same derated capacity, not nameplate.
    assert cold.reserve_wh < warm.reserve_wh


def test_a_healthy_snapshot_raises_nothing_and_is_operational_ok(
    app_with_graph: FastAPI,
) -> None:
    snapshot = TelemetrySnapshot.model_validate(
        _snapshot("t", soc_fraction=0.95, remaining_leg_m=200.0, remaining_hover_s=0.0)
    )
    _, alerts = evaluate_replan(
        aircraft=_AIRCRAFT,
        payload=_PAYLOAD,
        snapshot=snapshot,
        briefed_margin_wh=100.0,
        reserve_percent=20.0,
        age_s=1.0,
    )
    assert alerts == []


@pytest.mark.parametrize("field", ["thread_id", "ts", "soc_fraction", "remaining_leg_m", "oat_c"])
def test_a_snapshot_missing_a_required_field_is_rejected(field: str) -> None:
    from pydantic import ValidationError

    body = _snapshot("t")
    body.pop(field)
    with pytest.raises(ValidationError):
        TelemetrySnapshot.model_validate(body)


def test_unknown_snapshot_fields_are_rejected() -> None:
    """Telemetry is an input surface. Extra keys are refused, not carried."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TelemetrySnapshot.model_validate(_snapshot("t", decision="go"))
