"""An opt-in overlap window for a rotated API key, bound to its last client IP.

Rotation (#83) refuses the old key at once. ``SUAS_RETIRED_API_KEYS`` lets an
operator keep it working for a short, explicit window, but only from the exact
client IP that last used it successfully before the rotation, so a leaked key
used from anywhere else is still refused. Everything else gets the same 401 as
an unknown key. The peer address is the client; ``X-Forwarded-For`` counts only
when the peer is a configured trusted proxy.
"""

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.key_overlap import last_ip, record_key_use
from suas.api.security import session_key
from suas.config import Settings, get_settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import ApiKeyLastSeenRow
from tests.test_ack import _BODY
from tests.test_shared_rate_limit import postgres_url

__all__ = ["postgres_url"]  # a fixture, used by name

_OLD = "alpha-old-key"
_NEW = "alpha-new-key"
_HOME = "203.0.113.7"
_ELSEWHERE = "198.51.100.9"
_PROXY = "10.0.0.2"
_SECRET = "session-secret-0123456789abcdef0123"  # noqa: S105 (test fixture)

Configure = Callable[[Settings], None]


def _at(minutes: float) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _rotated(minutes: float = 10, **extra: Any) -> Settings:
    return Settings(
        api_keys=f"alpha:{_NEW}", retired_api_keys=f"alpha:{_OLD}@{_at(minutes)}", **extra
    )


def _client(app: FastAPI, ip: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 50000))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def configure(app_with_graph: FastAPI) -> Configure:
    def apply(settings: Settings) -> None:
        app_with_graph.dependency_overrides[get_settings] = lambda: settings

    return apply


async def _plan_before_rotation(app: FastAPI, configure: Configure) -> str:
    configure(Settings(api_keys=f"alpha:{_OLD}"))
    async with _client(app, _HOME) as client:
        created = await client.post("/api/plan", json=_BODY, headers={"X-API-Key": _OLD})
    assert created.status_code == 200
    return f"/api/plan/{created.json()['thread_id']}"


async def _get(app: FastAPI, ip: str, path: str, **headers: str) -> httpx.Response:
    async with _client(app, ip) as client:
        return await client.get(path, headers=headers)


async def _unknown_key_response(app: FastAPI, path: str) -> httpx.Response:
    return await _get(app, _HOME, path, **{"X-API-Key": "never-configured"})


async def test_the_old_key_works_from_its_last_ip_within_the_window(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated())

    response = await _get(app_with_graph, _HOME, path, **{"X-API-Key": _OLD})

    assert response.status_code == 200
    assert response.json()["found"] is True


async def test_the_old_key_from_another_ip_is_an_unknown_key(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated())

    refused = await _get(app_with_graph, _ELSEWHERE, path, **{"X-API-Key": _OLD})
    unknown = await _unknown_key_response(app_with_graph, path)

    assert refused.status_code == 401
    assert (refused.json(), refused.headers.get("www-authenticate")) == (
        unknown.json(),
        unknown.headers.get("www-authenticate"),
    )


async def test_the_old_key_is_refused_once_the_window_has_passed(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated(minutes=-1))

    assert (await _get(app_with_graph, _HOME, path, **{"X-API-Key": _OLD})).status_code == 401


async def test_a_key_never_used_before_rotation_has_no_ip_to_match(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    configure(_rotated())

    response = await _get(app_with_graph, _HOME, "/api/plan/none", **{"X-API-Key": _OLD})

    assert response.status_code == 401


async def test_a_spoofed_forwarded_for_is_ignored_without_a_trusted_proxy(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated())

    spoofed = {"X-API-Key": _OLD, "X-Forwarded-For": _HOME}
    assert (await _get(app_with_graph, _ELSEWHERE, path, **spoofed)).status_code == 401


async def test_forwarded_for_from_an_untrusted_peer_is_ignored(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated(trusted_proxies=_PROXY))

    spoofed = {"X-API-Key": _OLD, "X-Forwarded-For": _HOME}
    assert (await _get(app_with_graph, _ELSEWHERE, path, **spoofed)).status_code == 401


async def test_a_trusted_proxy_forwards_the_client_ip(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    configure(Settings(api_keys=f"alpha:{_OLD}", trusted_proxies=_PROXY))
    forwarded = {"X-API-Key": _OLD, "X-Forwarded-For": f"{_ELSEWHERE}, {_HOME}"}
    async with _client(app_with_graph, _PROXY) as client:
        created = await client.post("/api/plan", json=_BODY, headers=forwarded)
    path = f"/api/plan/{created.json()['thread_id']}"
    configure(_rotated(trusted_proxies=_PROXY))

    # The rightmost address the trusted proxy appended is the client; anything
    # to its left was supplied by the client and proves nothing.
    assert (await _get(app_with_graph, _PROXY, path, **forwarded)).status_code == 200
    direct = {"X-API-Key": _OLD, "X-Forwarded-For": _ELSEWHERE}
    assert (await _get(app_with_graph, _PROXY, path, **direct)).status_code == 401


@pytest.mark.parametrize("ip", [_HOME, _ELSEWHERE])
async def test_the_new_key_works_from_anywhere(
    app_with_graph: FastAPI, configure: Configure, ip: str
) -> None:
    path = await _plan_before_rotation(app_with_graph, configure)
    configure(_rotated())

    response = await _get(app_with_graph, ip, path, **{"X-API-Key": _NEW})

    assert response.json()["found"] is True


async def _seen(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with session_factory() as session:
        rows = (await session.execute(select(ApiKeyLastSeenRow))).scalars()
        return {row.key_hash: row.client_ip for row in rows}


async def test_the_last_ip_is_kept_by_key_hash_never_the_key(
    app_with_graph: FastAPI,
    configure: Configure,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _plan_before_rotation(app_with_graph, configure)
    await _get(app_with_graph, _ELSEWHERE, "/api/plan/none", **{"X-API-Key": _OLD})

    seen = await _seen(session_factory)

    assert seen == {hashlib.sha256(_OLD.encode()).hexdigest(): _ELSEWHERE}


async def test_session_keys_record_no_ip(
    app_with_graph: FastAPI,
    configure: Configure,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Browser keys arrive from the Next server, so its IP would say nothing
    # about the browser; session-secret rotation keeps its own rules (#83).
    configure(Settings(session_key_secret=_SECRET))
    browser = session_key(_SECRET, "S" * 43)

    response = await _get(app_with_graph, _HOME, "/api/plan/none", **{"X-API-Key": browser})

    assert response.status_code == 200
    assert await _seen(session_factory) == {}


@pytest.mark.parametrize(
    ("retired", "message"),
    [
        (f"alpha:{_OLD}", "operator_id:key@expiry"),
        (f"alpha:{_OLD}@not-a-time", "operator_id:key@expiry"),
        (f"alpha:{_OLD}@2026-10-26T12:00:00", "time zone"),
        (f"alpha:{_OLD}@{_at(24 * 60)}", "SUAS_RETIRED_KEY_MAX_GRACE_S"),
        (f"bravo:{_OLD}@{_at(10)}", "configured operator"),
        (f"alpha:{_NEW}@{_at(10)}", "still a current key"),
        (f"alpha:{_OLD}@{_at(10)},alpha:{_OLD}@{_at(5)}", "must not repeat a key"),
    ],
)
def test_a_retired_key_list_that_cannot_be_honoured_is_refused(retired: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(api_keys=f"alpha:{_NEW}", retired_api_keys=retired)


def test_the_overlap_is_off_and_no_proxy_is_trusted_by_default() -> None:
    settings = Settings()
    assert (settings.retired_api_keys, settings.trusted_proxies) == ("", "")
    assert settings.retired_key_max_grace_s == 3600


def test_uvicorn_does_not_rewrite_the_peer_address() -> None:
    # uvicorn trusts X-Forwarded-For from 127.0.0.1 by default and overwrites
    # the peer with it; SUAS_TRUSTED_PROXIES must be the only authority.
    entrypoint = Path(__file__).parents[1] / "scripts" / "docker-entrypoint.sh"
    assert "--no-proxy-headers" in entrypoint.read_text()


def test_ops_documents_the_overlap_window() -> None:
    docs = Path(__file__).parents[2] / "docs"
    ops = docs / "ops.md"
    rotation = ops.read_text().split("## Key rotation", 1)[1].split("\n## ", 1)[0]
    for phrase in (
        "SUAS_RETIRED_API_KEYS",
        "SUAS_RETIRED_KEY_MAX_GRACE_S",
        "SUAS_TRUSTED_PROXIES",
        "same client IP",
        "session secret",
    ):
        assert phrase in rotation
    assert "There is no overlap window" not in rotation
    assert "SUAS_RETIRED_API_KEYS" in (docs / "threat-model.md").read_text()


async def _moves_with_the_key(url: str) -> list[str | None]:
    engine = create_engine(url)
    await create_schema(engine)
    factory = create_session_factory(engine)
    try:
        seen = []
        for ip in (_HOME, _HOME, _ELSEWHERE):
            await record_key_use(factory, _OLD, ip)
            seen.append(await last_ip(factory, _OLD))
        seen.append(await last_ip(factory, _NEW))
        return seen
    finally:
        await engine.dispose()


async def test_the_recorded_ip_follows_the_key_on_sqlite(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'seen.db'}"
    assert await _moves_with_the_key(url) == [_HOME, _HOME, _ELSEWHERE, None]


async def test_the_recorded_ip_follows_the_key_on_postgres(postgres_url: str) -> None:
    assert await _moves_with_the_key(postgres_url) == [_HOME, _HOME, _ELSEWHERE, None]


def test_ci_runs_the_postgres_upsert() -> None:
    import yaml

    ci = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    steps = yaml.safe_load(ci.read_text(encoding="utf-8"))["jobs"]["postgres-integration"]["steps"]
    assert any("test_retired_keys.py" in step.get("run", "") for step in steps)
