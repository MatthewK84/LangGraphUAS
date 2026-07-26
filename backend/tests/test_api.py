"""API tests.

These exercise routing, validation, auth, rate limiting, and the ops endpoints
with the graph and database overridden so no network or model call occurs.
ASGITransport is used so the production lifespan does not run.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from suas.api.security import require_api_key
from suas.config import Settings, get_settings

_VALID_BODY: dict[str, Any] = {
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


async def test_health_endpoint(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"


async def test_health_sets_request_id_header(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/health")
    assert response.headers.get("X-Request-ID")


async def test_request_id_is_echoed_when_supplied(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/health", headers={"X-Request-ID": "trace-abc"})
    assert response.headers["X-Request-ID"] == "trace-abc"


async def test_readiness_reports_database_ok(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["database"] == "ok"


async def test_aircraft_catalog_returns_seeded_platforms(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/api/aircraft")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert "Skydio_X10D" in ids
    assert "Freefly_Astro_Max" in ids


async def test_payload_catalog_returns_seeded_payloads(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/api/payloads")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert "None" in ids


async def test_plan_endpoint_returns_result(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=_VALID_BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["report"] == "TEST REPORT"
    assert body["thread_id"]
    assert body["degraded"] is False
    assert body["warnings"] == []


async def test_plan_endpoint_rejects_bad_coordinates(app_with_graph: FastAPI) -> None:
    bad = {**_VALID_BODY, "mission_params": {**_VALID_BODY["mission_params"], "latitude": 999.0}}
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=bad)
    assert response.status_code == 422


async def test_thread_state_roundtrip(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_VALID_BODY)
        thread_id = created.json()["thread_id"]
        fetched = await client.get(f"/api/plan/{thread_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["found"] is True
    assert body["thread_id"] == thread_id
    assert body["report"] == "TEST REPORT"


async def test_thread_state_unknown_thread_reports_not_found(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.get("/api/plan/does-not-exist")
    assert response.status_code == 200
    assert response.json()["found"] is False


async def test_metrics_endpoint_exposes_counters(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        await client.post("/api/plan", json=_VALID_BODY)
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "suas_http_requests_total" in response.text
    assert "suas_plan_outcomes_total" in response.text


async def test_plan_requires_api_key_when_enabled(app_with_graph: FastAPI) -> None:
    app_with_graph.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    app_with_graph.dependency_overrides.pop(require_api_key, None)
    async with _client(app_with_graph) as client:
        unauth = await client.post("/api/plan", json=_VALID_BODY)
        authed = await client.post("/api/plan", json=_VALID_BODY, headers={"X-API-Key": "secret"})
    assert unauth.status_code == 401
    assert authed.status_code == 200


@pytest.mark.parametrize("limit", [2])
async def test_rate_limit_returns_429_after_allowance(app_with_graph: FastAPI, limit: int) -> None:
    app_with_graph.dependency_overrides[get_settings] = lambda: Settings(
        rate_limit_requests=limit,
        rate_limit_window_s=60.0,
    )
    from suas.api.ratelimit import SlidingWindowLimiter

    app_with_graph.state.limiter = SlidingWindowLimiter(max_requests=limit, window_s=60.0)
    async with _client(app_with_graph) as client:
        codes = [
            (await client.post("/api/plan", json=_VALID_BODY)).status_code
            for _ in range(limit + 1)
        ]
    assert codes[:limit] == [200] * limit
    assert codes[-1] == 429
