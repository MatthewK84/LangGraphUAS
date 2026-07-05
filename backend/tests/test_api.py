"""API tests.

These exercise the HTTP layer with the real routing and validation, but with
the compiled graph and settings overridden so no database, network, or model is
touched. ASGITransport is used so the production lifespan does not run.
"""

from typing import Any

import httpx
from langgraph.graph.state import CompiledStateGraph

from suas.api.dependencies import get_graph
from suas.api.security import require_api_key
from suas.config import Settings, get_settings
from suas.main import create_app

_VALID_BODY: dict[str, Any] = {
    "aircraft_id": "DJI_M350",
    "payload_id": "Zenmuse_H30T",
    "mission_params": {
        "distance_m": 2000.0,
        "hover_time_s": 120.0,
        "target_altitude_m": 120.0,
        "elevation_m": 0.0,
        "latitude": 34.0,
        "longitude": -80.0,
    },
}


def _client(app: httpx.URL | Any) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_endpoint() -> None:
    app = create_app()
    async with _client(app) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"


async def test_plan_endpoint_returns_result(graph: CompiledStateGraph) -> None:
    app = create_app()
    app.dependency_overrides[get_graph] = lambda: graph
    async with _client(app) as client:
        response = await client.post("/api/plan", json=_VALID_BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["report"] == "TEST REPORT"
    assert body["thread_id"]


async def test_plan_endpoint_rejects_bad_coordinates(graph: CompiledStateGraph) -> None:
    app = create_app()
    app.dependency_overrides[get_graph] = lambda: graph
    bad_body = {**_VALID_BODY, "mission_params": {**_VALID_BODY["mission_params"], "latitude": 999.0}}
    async with _client(app) as client:
        response = await client.post("/api/plan", json=bad_body)
    assert response.status_code == 422


async def test_plan_endpoint_requires_api_key_when_enabled(graph: CompiledStateGraph) -> None:
    app = create_app()
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="secret")
    app.dependency_overrides.pop(require_api_key, None)
    async with _client(app) as client:
        unauth = await client.post("/api/plan", json=_VALID_BODY)
        authed = await client.post(
            "/api/plan",
            json=_VALID_BODY,
            headers={"X-API-Key": "secret"},
        )
    assert unauth.status_code == 401
    assert authed.status_code == 200
