"""A client-chosen thread id cannot pose as another thread's replan child.

A replan runs on ``<parent>:<n>``, and ownership of an id with a ``:`` falls
back to its parent. Before this, ``POST /api/plan`` took any string as
``thread_id``, so one operator could plan onto ``<another's id>:1`` before that
thread's first replan, own the row, and read the replan that landed there.

New ids are now letters, digits, ``_`` and ``-``, 1 to 128 characters, so a
``:`` id can only be one the server handed out. Lookups (GET, ack, replan) stay
lenient so ids stored before this keep working; they are only bounded at 255
characters, the bound replan already had. Validation is syntactic and runs
before any lookup, so a refusal says nothing about what exists.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.routes import _visible_to
from suas.config import Settings, get_settings
from suas.db.retention import record_thread
from tests.test_ack import _BODY
from tests.test_replan import _snapshot

_ALPHA = {"X-API-Key": "alpha-secret"}
_BRAVO = {"X-API-Key": "bravo-secret"}
_ROOT = Path(__file__).resolve().parents[2]


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def keyed_app(app_with_graph: FastAPI) -> FastAPI:
    settings = Settings(api_keys="alpha:alpha-secret,bravo:bravo-secret")
    app_with_graph.dependency_overrides[get_settings] = lambda: settings
    return app_with_graph


async def _plan(
    client: httpx.AsyncClient, thread_id: str | None, **headers: str
) -> httpx.Response:
    return await client.post("/api/plan", json={**_BODY, "thread_id": thread_id}, headers=headers)


# --- new ids --------------------------------------------------------------------


@pytest.mark.parametrize(
    "thread_id",
    ["mission-1", "A_b-9", "0f8fad5b-d9cb-469f-a165-70867728950e", "x" * 128],
)
async def test_a_plain_new_id_is_accepted(app_with_graph: FastAPI, thread_id: str) -> None:
    async with _client(app_with_graph) as client:
        response = await _plan(client, thread_id)
    assert response.status_code == 200
    assert response.json()["thread_id"] == thread_id


@pytest.mark.parametrize(
    "thread_id",
    ["parent:1", "a:b", ":", "", "x" * 129, "has space", "dot.ted", "slash/ed", "ünï", "tab\t"],
)
async def test_a_new_id_outside_the_format_is_422(app_with_graph: FastAPI, thread_id: str) -> None:
    async with _client(app_with_graph) as client:
        response = await _plan(client, thread_id)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "thread_id"]


async def test_no_id_still_gets_a_server_generated_one(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await _plan(client, None)
    assert response.status_code == 200
    assert ":" not in response.json()["thread_id"]


# --- the impersonation ----------------------------------------------------------


async def test_an_operator_cannot_squat_on_a_future_replan_id(keyed_app: FastAPI) -> None:
    # Once bravo's thread exists its children are bravo's, so the squat has to
    # come first, on an id bravo will choose later.
    async with _client(keyed_app) as client:
        squat = await _plan(client, "mission-7:1", **_ALPHA)
        victim = await _plan(client, "mission-7", **_BRAVO)
        replan = await client.post("/api/replan", json=_snapshot("mission-7"), headers=_BRAVO)

    assert squat.status_code == 422
    assert victim.status_code == 200
    assert replan.status_code == 200
    assert replan.json()["thread_id"] == "mission-7:1"


def _without_input(response: httpx.Response) -> Any:
    return [{k: v for k, v in e.items() if k != "input"} for e in response.json()["detail"]]


async def test_the_refusal_is_the_same_whether_the_parent_exists(keyed_app: FastAPI) -> None:
    # Before this a ':' id under bravo's thread got 404 and a free one 200.
    async with _client(keyed_app) as client:
        victim = (await _plan(client, None, **_BRAVO)).json()["thread_id"]
        taken = await _plan(client, f"{victim}:1", **_ALPHA)
        free = await _plan(client, "never-planned:1", **_ALPHA)

    assert taken.status_code == free.status_code == 422
    assert _without_input(taken) == _without_input(free)


async def test_a_stored_colon_id_belongs_to_its_parents_owner(
    keyed_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    # A row planned before this fix, squatting on bravo's first replan id.
    async with _client(keyed_app) as client:
        victim = (await _plan(client, None, **_BRAVO)).json()["thread_id"]
    async with session_factory() as session:
        await record_thread(session, f"{victim}:1", "alpha")

    assert not await _visible_to(session_factory, f"{victim}:1", "alpha")
    assert await _visible_to(session_factory, f"{victim}:1", "bravo")


async def test_a_stored_colon_id_with_no_parent_stays_its_owners(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await record_thread(session, "orphan:1", "alpha")

    assert await _visible_to(session_factory, "orphan:1", "alpha")
    assert not await _visible_to(session_factory, "orphan:1", "bravo")


# --- lookups --------------------------------------------------------------------


async def test_lookups_still_serve_ids_stored_before_the_format(
    app_with_graph: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await record_thread(session, "legacy id.1")
    async with _client(app_with_graph) as client:
        fetched = await client.get("/api/plan/legacy id.1")
        acked = await client.post(
            "/api/plan/legacy id.1/ack", json={"action": "confirm", "actor": "x"}
        )
        replanned = await client.post("/api/replan", json=_snapshot("legacy id.1"))

    assert fetched.status_code == 200
    assert fetched.json()["found"] is False  # no checkpoint, but not refused
    assert acked.status_code != 422
    assert replanned.status_code != 422


async def test_lookups_refuse_an_id_no_thread_can_have(app_with_graph: FastAPI) -> None:
    too_long = "x" * 256
    async with _client(app_with_graph) as client:
        fetched = await client.get(f"/api/plan/{too_long}")
        acked = await client.post(
            f"/api/plan/{too_long}/ack", json={"action": "confirm", "actor": "x"}
        )
        replanned = await client.post("/api/replan", json=_snapshot(too_long))

    assert [fetched.status_code, acked.status_code, replanned.status_code] == [422, 422, 422]


async def test_a_lookup_of_the_longest_valid_id_is_not_refused(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        fetched = await client.get(f"/api/plan/{'x' * 255}")
    assert fetched.status_code == 200


# --- docs -----------------------------------------------------------------------


def test_the_readme_and_threat_model_state_the_format() -> None:
    for doc in ("README.md", "docs/threat-model.md"):
        assert "[A-Za-z0-9_-]{1,128}" in (_ROOT / doc).read_text(), doc
