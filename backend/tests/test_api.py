"""API tests.

These exercise routing, validation, auth, rate limiting, and the ops endpoints
with the graph and database overridden so no network or model call occurs.
ASGITransport is used so the production lifespan does not run.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.security import require_api_key
from suas.config import Settings, get_settings
from suas.db.migrations import EXPECTED_REVISION, MigrationState, migration_state
from tests.conftest import stamp_revision

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
    assert body == {"ready": True, "database": "ok", "migrations": "ok", "checkpointer": "ok"}


async def test_a_schema_behind_the_code_is_not_ready(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The failure #111 names: an unmigrated container reported ready."""
    async with session_factory() as session, session.begin():
        await stamp_revision(await session.connection(), "0009")

    async with _client(app_with_graph) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["migrations"] == "pending"
    assert response.json()["ready"] is False


async def test_an_untracked_postgres_schema_is_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Tables made by create_all with no alembic_version row are not migrated."""
    async with session_factory() as session:
        await session.execute(text("DROP TABLE alembic_version"))
        assert await migration_state(session, tracked_required=True) is MigrationState.PENDING
        assert await migration_state(session, tracked_required=False) is (
            MigrationState.NOT_TRACKED
        )


async def test_local_sqlite_without_alembic_stays_ready(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Local SQLite schemas come from create_all, so no version table is expected there."""
    async with session_factory() as session, session.begin():
        await session.execute(text("DROP TABLE alembic_version"))

    async with _client(app_with_graph) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["migrations"] == "not_tracked"


class _BrokenSaver:
    async def aget_tuple(self, config: Any) -> None:
        _ = config
        raise ConnectionError("checkpoint store unreachable")


class _GraphWithBrokenSaver:
    checkpointer = _BrokenSaver()


async def test_an_unreachable_checkpointer_is_not_ready(app_with_graph: FastAPI) -> None:
    app_with_graph.state.graph = _GraphWithBrokenSaver()

    async with _client(app_with_graph) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checkpointer"] == "unavailable"


async def test_readiness_does_not_need_a_model_key(
    app_with_graph: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Advisory briefs are a supported mode, so a missing model key still takes traffic."""
    monkeypatch.setenv("SUAS_OPENAI_API_KEY", "")
    get_settings.cache_clear()

    async with _client(app_with_graph) as client:
        response = await client.get("/ready")

    get_settings.cache_clear()
    assert response.status_code == 200


def test_the_expected_revision_is_the_alembic_head() -> None:
    """A new migration must bump EXPECTED_REVISION, or every container reads as pending."""
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parent.parent / "alembic")
    )
    assert ScriptDirectory.from_config(config).get_heads() == [EXPECTED_REVISION]


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


async def test_plan_endpoint_returns_an_assessment_awaiting_acknowledgement(
    app_with_graph: FastAPI,
) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=_VALID_BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["awaiting_ack"] is True
    assert body["report"] == ""
    assert body["assessment"]["inputs_hash"]
    assert body["thread_id"]
    assert body["degraded"] is False
    assert body["warnings"] == []


async def test_every_watt_on_the_plan_says_what_it_rests_on(app_with_graph: FastAPI) -> None:
    """The wire could not tell a datasheet watt from a derived one (#79)."""
    async with _client(app_with_graph) as client:
        body = (await client.post("/api/plan", json=_VALID_BODY)).json()
    provenance = body["provenance"]
    hover = provenance["effective_hover_power_w"]
    # The airframe's hover figure is derived, but no payload records its mass.
    assert hover["source"] == "unknown"
    assert hover["confidence"] == "low"
    assert hover["operational_grade"] is False
    assert "aircraft.hover_power_w" in hover["inputs"]
    assert provenance["battery_check.usable_capacity_wh"]["inputs"] == ["aircraft.battery_wh"]
    assert body["calculations"]["effective_hover_power_w"] > 0


async def test_plan_endpoint_rejects_bad_coordinates(app_with_graph: FastAPI) -> None:
    bad = {**_VALID_BODY, "mission_params": {**_VALID_BODY["mission_params"], "latitude": 999.0}}
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=bad)
    assert response.status_code == 422


async def test_thread_state_roundtrip(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        created = await client.post("/api/plan", json=_VALID_BODY)
        thread_id = created.json()["thread_id"]
        acked = await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "tester"},
        )
        fetched = await client.get(f"/api/plan/{thread_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["found"] is True
    assert body["thread_id"] == thread_id
    assert body["report"] == "TEST REPORT"
    assert body["provenance"]["energy_required_wh"]["source"] == "unknown"
    assert acked.json()["provenance"] == body["provenance"]


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


@pytest.mark.parametrize("limit", [1, 2])
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
