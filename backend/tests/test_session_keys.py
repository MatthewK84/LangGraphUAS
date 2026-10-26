"""Anonymous per-browser operators (#82).

The dashboard proxy used to send one backend key for every browser, so two
people on one deployment were one operator and #81's isolation was decorative.
With SUAS_SESSION_KEY_SECRET set, the proxy gives each browser a random session
id and presents ``session.<id>.<HMAC-SHA256(secret, id)>``; the backend checks
the MAC and treats each session as its own operator. The secret lives only on
the two servers; the browser holds nothing but its own session id.
"""

import hashlib
import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.rate_limit_dep import _client_key
from suas.api.security import session_key
from suas.config import (
    DEMO_SESSION_KEY_SECRET,
    MIN_SESSION_SECRET_LENGTH,
    Settings,
    get_settings,
)
from suas.db.retention import get_acknowledgement
from suas.main import warn_on_weak_auth
from tests.test_ack import _BODY
from tests.test_replan import _snapshot

_SECRET = "test-only-session-secret-0123456789abcdef"  # noqa: S105 (test fixture)
_SESSION_A = "A" * 43
_SESSION_B = "b" * 22 + "_-" + "9" * 19
_NEVER_PLANNED = "00000000-0000-4000-8000-000000000000"

# Shared with frontend/src/lib/server/session.test.ts: both sides must derive
# the same key from the same secret and session id, or no browser can sign in.
_VECTOR_KEY = (
    "session.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA."
    "c3543da27fae09625f09f2a3106025813d7ea42b0d8924bb8e08786a76ee710b"
)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _as(session_id: str) -> dict[str, str]:
    return {"X-API-Key": session_key(_SECRET, session_id)}


@pytest.fixture
def session_app(app_with_graph: FastAPI) -> FastAPI:
    settings = Settings(session_key_secret=_SECRET, api_keys="ops:ops-secret")
    app_with_graph.dependency_overrides[get_settings] = lambda: settings
    return app_with_graph


async def _plan(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    created = await client.post("/api/plan", json=_BODY, headers=headers)
    assert created.status_code == 200
    body: dict[str, Any] = created.json()
    return body


def _without_thread_id(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "thread_id"}


# --- the key -------------------------------------------------------------------


def test_the_key_is_the_session_id_and_its_mac() -> None:
    assert session_key(_SECRET, _SESSION_A) == _VECTOR_KEY
    assert session_key(_SECRET, _SESSION_A) != session_key(_SECRET + "x", _SESSION_A)


def test_session_mode_turns_auth_on() -> None:
    assert Settings(session_key_secret=_SECRET).auth_enabled
    assert not Settings(session_key_secret="").auth_enabled


def test_a_short_secret_refuses_to_start() -> None:
    with pytest.raises(ValidationError):
        Settings(session_key_secret="too-short")  # noqa: S106 (test fixture)


# --- isolation -----------------------------------------------------------------


async def test_two_browsers_cannot_read_each_others_threads(session_app: FastAPI) -> None:
    async with _client(session_app) as client:
        thread_id = (await _plan(client, _as(_SESSION_A)))["thread_id"]
        own = await client.get(f"/api/plan/{thread_id}", headers=_as(_SESSION_A))
        other = await client.get(f"/api/plan/{thread_id}", headers=_as(_SESSION_B))
        absent = await client.get(f"/api/plan/{_NEVER_PLANNED}", headers=_as(_SESSION_B))

    assert own.json()["found"] is True
    assert other.status_code == absent.status_code == 200
    assert _without_thread_id(other.json()) == _without_thread_id(absent.json())


async def test_two_browsers_cannot_acknowledge_each_others_threads(
    session_app: FastAPI,
) -> None:
    ack = {"action": "confirm", "actor": "other-browser"}
    async with _client(session_app) as client:
        thread_id = (await _plan(client, _as(_SESSION_A)))["thread_id"]
        other = await client.post(f"/api/plan/{thread_id}/ack", json=ack, headers=_as(_SESSION_B))
        absent = await client.post(
            f"/api/plan/{_NEVER_PLANNED}/ack", json=ack, headers=_as(_SESSION_B)
        )
        own = await client.post(f"/api/plan/{thread_id}/ack", json=ack, headers=_as(_SESSION_A))

    assert other.status_code == absent.status_code == 404
    assert other.json() == absent.json()
    assert own.status_code == 200


async def test_two_browsers_cannot_replan_each_others_threads(session_app: FastAPI) -> None:
    async with _client(session_app) as client:
        thread_id = (await _plan(client, _as(_SESSION_A)))["thread_id"]
        await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "a"},
            headers=_as(_SESSION_A),
        )
        other = await client.post(
            "/api/replan", json=_snapshot(thread_id), headers=_as(_SESSION_B)
        )
        absent = await client.post(
            "/api/replan", json=_snapshot(_NEVER_PLANNED), headers=_as(_SESSION_B)
        )

    assert other.status_code == absent.status_code == 404
    assert other.json() == absent.json()


async def test_a_session_and_a_configured_key_are_different_operators(
    session_app: FastAPI,
) -> None:
    async with _client(session_app) as client:
        thread_id = (await _plan(client, {"X-API-Key": "ops-secret"}))["thread_id"]
        from_session = await client.get(f"/api/plan/{thread_id}", headers=_as(_SESSION_A))
        from_ops = await client.get(f"/api/plan/{thread_id}", headers={"X-API-Key": "ops-secret"})

    assert from_session.json()["found"] is False
    assert from_ops.json()["found"] is True


@pytest.mark.parametrize(
    "presented",
    [
        session_key(_SECRET, _SESSION_A)[:-1] + "0",  # forged MAC
        session_key("another-secret-of-sufficient-length-xx", _SESSION_A),
        f"session.{_SESSION_A}",  # no MAC
        "session.short." + session_key(_SECRET, "short").rpartition(".")[2],  # id too short
        "session.bad!chars!" + "x" * 30 + "." + "0" * 64,
    ],
)
async def test_a_session_key_the_secret_did_not_sign_is_refused(
    session_app: FastAPI, presented: str
) -> None:
    async with _client(session_app) as client:
        response = await client.post("/api/plan", json=_BODY, headers={"X-API-Key": presented})
    assert response.status_code == 401


async def test_without_the_secret_a_session_key_is_just_a_wrong_key(
    app_with_graph: FastAPI,
) -> None:
    app_with_graph.dependency_overrides[get_settings] = lambda: Settings(api_keys="ops:ops-secret")
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=_BODY, headers=_as(_SESSION_A))
    assert response.status_code == 401


async def test_without_a_secret_a_key_signed_with_an_empty_secret_is_refused(
    app_with_graph: FastAPI,
) -> None:
    # Unconfigured must mean off: an empty secret is public, so anyone can sign with it.
    app_with_graph.dependency_overrides[get_settings] = lambda: Settings(api_keys="ops:ops-secret")
    forged = {"X-API-Key": session_key("", _SESSION_A)}
    async with _client(app_with_graph) as client:
        response = await client.post("/api/plan", json=_BODY, headers=forged)
    assert response.status_code == 401


def test_a_secret_of_exactly_the_minimum_length_starts() -> None:
    secret = "s" * MIN_SESSION_SECRET_LENGTH
    assert Settings(session_key_secret=secret).auth_enabled
    with pytest.raises(ValidationError):
        Settings(session_key_secret=secret[:-1])


async def test_the_mission_row_holds_a_digest_not_the_session_id(
    session_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A database reader must not get a cookie value they could replay through the proxy."""
    async with _client(session_app) as client:
        thread_id = (await _plan(client, _as(_SESSION_A)))["thread_id"]
    async with session_factory() as session:
        row = await get_acknowledgement(session, thread_id)

    digest = hashlib.sha256(_SESSION_A.encode()).hexdigest()[:32]
    assert row is not None and row.operator_key_id == f"session:{digest}"
    assert _SESSION_A not in row.operator_key_id


async def test_no_response_carries_the_secret_or_a_key(session_app: FastAPI) -> None:
    async with _client(session_app) as client:
        plan = await client.post("/api/plan", json=_BODY, headers=_as(_SESSION_A))
    exposed = plan.text + str(dict(plan.headers))
    assert _SECRET not in exposed
    assert session_key(_SECRET, _SESSION_A).rpartition(".")[2] not in exposed


def test_every_session_shares_one_rate_limit_bucket() -> None:
    """Minting a fresh cookie must not mint a fresh allowance (see #84)."""

    class _Request:
        client = None

    first = _client_key(_Request(), session_key(_SECRET, _SESSION_A))  # type: ignore[arg-type]
    second = _client_key(_Request(), session_key(_SECRET, _SESSION_B))  # type: ignore[arg-type]
    assert first == second == "sessions"


@pytest.mark.parametrize(
    ("secret", "warned"),
    [(DEMO_SESSION_KEY_SECRET, True), (_SECRET, False)],
)
def test_the_public_demo_secret_is_named_at_startup(
    caplog: pytest.LogCaptureFixture, secret: str, warned: bool
) -> None:
    with caplog.at_level(logging.WARNING, logger="suas.main"):
        warn_on_weak_auth(Settings(session_key_secret=secret))
    assert ("DEMO session secret in use" in caplog.text) is warned
