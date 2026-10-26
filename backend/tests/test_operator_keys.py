"""Per-operator API keys (#81).

One shared key meant any valid caller could read any thread: the thread id was
the only thing between two operators. Each key now has an id, every mission
records the id of the key that planned it, and a thread is visible only to that
key. A refusal looks exactly like a thread that does not exist, so a caller
holding someone else's thread id learns nothing from asking.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.routes import _visible_to
from suas.config import LEGACY_OPERATOR_ID, Settings, get_settings
from suas.db.retention import get_acknowledgement, record_thread
from tests.test_ack import _BODY
from tests.test_replan import _snapshot

_ALPHA = {"X-API-Key": "alpha-secret"}
_BRAVO = {"X-API-Key": "bravo-secret"}
_BACKEND = Path(__file__).resolve().parent.parent
_NEVER_PLANNED = "00000000-0000-4000-8000-000000000000"


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def keyed_app(app_with_graph: FastAPI) -> FastAPI:
    """The test app with two operators, alpha and bravo."""
    settings = Settings(api_keys="alpha:alpha-secret,bravo:bravo-secret")
    app_with_graph.dependency_overrides[get_settings] = lambda: settings
    return app_with_graph


async def _plan(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    created = await client.post("/api/plan", json=_BODY, headers=headers)
    assert created.status_code == 200
    thread_id: str = created.json()["thread_id"]
    return thread_id


def _without_thread_id(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "thread_id"}


# --- configuration -----------------------------------------------------------


def test_each_key_is_named_by_its_operator_id() -> None:
    settings = Settings(api_keys="alpha:a-key, bravo:b-key")
    assert settings.operator_keys == {"alpha": "a-key", "bravo": "b-key"}
    assert settings.auth_enabled


def test_the_single_shared_key_still_works_as_the_default_operator() -> None:
    assert Settings(api_key="shared").operator_keys == {"default": "shared"}


def test_no_keys_means_auth_is_off() -> None:
    settings = Settings(api_key="", api_keys="")
    assert settings.operator_keys == {}
    assert not settings.auth_enabled


@pytest.mark.parametrize(
    ("api_keys", "api_key"),
    [
        ("alpha", ""),  # no separator
        (":a-key", ""),  # empty id
        ("alpha:", ""),  # empty key
        ("alpha:a-key,alpha:other", ""),  # duplicate id
        ("alpha:same,bravo:same", ""),  # one key, two operators
        ("default:a-key", "shared"),  # the legacy key's id is taken
        ("alpha:shared", "shared"),  # the legacy key is already alpha's
    ],
)
def test_an_ambiguous_key_list_refuses_to_start(api_keys: str, api_key: str) -> None:
    with pytest.raises(ValidationError):
        Settings(api_keys=api_keys, api_key=api_key)


# --- isolation ---------------------------------------------------------------


async def test_key_a_cannot_read_key_bs_thread(keyed_app: FastAPI) -> None:
    async with _client(keyed_app) as client:
        thread_id = await _plan(client, _ALPHA)
        own = await client.get(f"/api/plan/{thread_id}", headers=_ALPHA)
        other = await client.get(f"/api/plan/{thread_id}", headers=_BRAVO)
        absent = await client.get(f"/api/plan/{_NEVER_PLANNED}", headers=_BRAVO)

    assert own.json()["found"] is True
    assert other.status_code == absent.status_code
    assert _without_thread_id(other.json()) == _without_thread_id(absent.json())
    assert other.json()["found"] is False


async def test_key_a_cannot_acknowledge_key_bs_thread(
    keyed_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    ack = {"action": "confirm", "actor": "intruder"}
    async with _client(keyed_app) as client:
        thread_id = await _plan(client, _ALPHA)
        other = await client.post(f"/api/plan/{thread_id}/ack", json=ack, headers=_BRAVO)
        absent = await client.post(f"/api/plan/{_NEVER_PLANNED}/ack", json=ack, headers=_BRAVO)
        still_pending = await client.get(f"/api/plan/{thread_id}", headers=_ALPHA)

    assert other.status_code == absent.status_code == 404
    assert other.json() == absent.json()
    assert still_pending.json()["awaiting_ack"] is True
    async with session_factory() as session:
        row = await get_acknowledgement(session, thread_id)
    assert row is not None and row.ack_actor is None


async def test_key_a_cannot_replan_key_bs_thread(keyed_app: FastAPI) -> None:
    async with _client(keyed_app) as client:
        thread_id = await _plan(client, _ALPHA)
        await client.post(
            f"/api/plan/{thread_id}/ack",
            json={"action": "confirm", "actor": "alpha"},
            headers=_ALPHA,
        )
        other = await client.post("/api/replan", json=_snapshot(thread_id), headers=_BRAVO)
        absent = await client.post("/api/replan", json=_snapshot(_NEVER_PLANNED), headers=_BRAVO)
        own = await client.post("/api/replan", json=_snapshot(thread_id), headers=_ALPHA)

    assert other.status_code == absent.status_code == 404
    assert other.json() == absent.json()
    assert own.status_code == 200


async def test_a_replan_child_belongs_to_its_parents_operator(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A child thread has no mission row of its own; its parent's owner holds it.

    Checked on the ownership rule rather than over HTTP: in the test app the
    replan graph keeps its own saver, so a child's state is not readable there
    even by its owner, while production shares one checkpointer.
    """
    async with session_factory() as session:
        await record_thread(session, "parent-thread", "alpha")

    assert await _visible_to(session_factory, "parent-thread:1", "alpha")
    assert not await _visible_to(session_factory, "parent-thread:1", "bravo")
    assert not await _visible_to(session_factory, "orphan:1", "alpha")


async def test_key_a_cannot_plan_onto_key_bs_thread(keyed_app: FastAPI) -> None:
    async with _client(keyed_app) as client:
        thread_id = await _plan(client, _ALPHA)
        before = (await client.get(f"/api/plan/{thread_id}", headers=_ALPHA)).json()
        hijack = await client.post(
            "/api/plan", json={**_BODY, "thread_id": thread_id}, headers=_BRAVO
        )
        after = (await client.get(f"/api/plan/{thread_id}", headers=_ALPHA)).json()

    assert hijack.status_code == 404
    assert after == before


async def test_each_mission_records_the_key_that_planned_it(
    keyed_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with _client(keyed_app) as client:
        alpha_thread = await _plan(client, _ALPHA)
        bravo_thread = await _plan(client, _BRAVO)

    async with session_factory() as session:
        alpha_row = await get_acknowledgement(session, alpha_thread)
        bravo_row = await get_acknowledgement(session, bravo_thread)
    assert alpha_row is not None and alpha_row.operator_key_id == "alpha"
    assert bravo_row is not None and bravo_row.operator_key_id == "bravo"


async def test_a_thread_with_no_mission_row_is_unknown_to_every_key(
    keyed_app: FastAPI, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Checkpoints older than the missions table have no owner, so nobody may read them."""
    from sqlalchemy import delete

    from suas.db.models import MissionThreadRow

    async with _client(keyed_app) as client:
        thread_id = await _plan(client, _ALPHA)
        async with session_factory() as session:
            await session.execute(
                delete(MissionThreadRow).where(MissionThreadRow.thread_id == thread_id)
            )
            await session.commit()
        orphan = await client.get(f"/api/plan/{thread_id}", headers=_ALPHA)

    assert orphan.json()["found"] is False


async def test_with_auth_off_every_caller_reads_every_thread(app_with_graph: FastAPI) -> None:
    """Local development has no keys and so no operators to separate."""
    async with _client(app_with_graph) as client:
        thread_id = (await client.post("/api/plan", json=_BODY)).json()["thread_id"]
        read = await client.get(f"/api/plan/{thread_id}")
    assert read.json()["found"] is True


def test_missions_planned_under_the_shared_key_stay_the_default_operators(
    tmp_path: Path,
) -> None:
    """Migration 0011 backfills existing missions, so the one-key deployment keeps them."""
    database = tmp_path / "upgrade.db"
    env = {**os.environ, "SUAS_DATABASE_URL": f"sqlite+aiosqlite:///{database}"}

    def alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_BACKEND,
            env=env,
            check=True,
            capture_output=True,
        )

    alembic("upgrade", "0010")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO mission_threads (thread_id, created_at) VALUES ('old', '2026-10-01')"
        )
    alembic("upgrade", "head")
    with sqlite3.connect(database) as connection:
        owner = connection.execute(
            "SELECT operator_key_id FROM mission_threads WHERE thread_id = 'old'"
        ).fetchone()
    assert owner == (LEGACY_OPERATOR_ID,)


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "alpha-secre"}, {"X-API-Key": ""}])
async def test_a_key_that_names_no_operator_is_refused(
    keyed_app: FastAPI, headers: dict[str, str]
) -> None:
    async with _client(keyed_app) as client:
        response = await client.post("/api/plan", json=_BODY, headers=headers)
    assert response.status_code == 401


async def test_a_thread_id_with_a_colon_and_its_own_row_is_its_own_owners(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Only a row-less child falls back to its parent; a caller-chosen 'x:9' does not."""
    async with session_factory() as session:
        await record_thread(session, "shared-prefix", "bravo")
        await record_thread(session, "shared-prefix:9", "alpha")

    assert await _visible_to(session_factory, "shared-prefix:9", "alpha")
    assert not await _visible_to(session_factory, "shared-prefix:9", "bravo")
