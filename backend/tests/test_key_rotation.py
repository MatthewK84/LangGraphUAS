"""Key rotation without breaking open interrupts (#83).

A key is rotated by restarting with a new value under the same operator id.
The mission's owner is the id, not the key, and the acknowledgement is bound to
the assessment's ``inputs_hash``, not to whichever key asked for it. So a plan
left waiting for a signature survives the rotation, the old key stops working
at once, and a stale signature is still refused. The same holds for the
session secret behind per-browser operators (#82): the operator is a digest of
the browser's session id, which the secret only signs.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from suas.api.security import session_key
from suas.config import Settings, get_settings
from tests.test_ack import _BODY

_OLD_SECRET = "old-session-secret-0123456789abcdef"  # noqa: S105 (test fixture)
_NEW_SECRET = "new-session-secret-fedcba9876543210"  # noqa: S105 (test fixture)
_SESSION = "R" * 43

Configure = Callable[[Settings], None]


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def configure(app_with_graph: FastAPI) -> Configure:
    """Swap the app's settings, as a restart with new environment would."""

    def apply(settings: Settings) -> None:
        app_with_graph.dependency_overrides[get_settings] = lambda: settings

    return apply


async def _open_interrupt(client: httpx.AsyncClient, key: str) -> dict[str, Any]:
    created = await client.post("/api/plan", json=_BODY, headers={"X-API-Key": key})
    assert created.status_code == 200
    body: dict[str, Any] = created.json()
    assert body["awaiting_ack"] is True
    return body


def _signature(plan: dict[str, Any], inputs_hash: str | None = None) -> dict[str, Any]:
    signed = inputs_hash or plan["assessment"]["inputs_hash"]
    return {"action": "confirm", "actor": "dispatcher-1", "inputs_hash": signed}


async def _assert_old_key_refused(
    client: httpx.AsyncClient, plan: dict[str, Any], old_key: str
) -> None:
    thread = f"/api/plan/{plan['thread_id']}"
    old = {"X-API-Key": old_key}
    assert (await client.get(thread, headers=old)).status_code == 401
    assert (
        await client.post(f"{thread}/ack", json=_signature(plan), headers=old)
    ).status_code == 401


async def _assert_new_key_signs(
    client: httpx.AsyncClient, plan: dict[str, Any], new_key: str
) -> None:
    thread = f"/api/plan/{plan['thread_id']}"
    new = {"X-API-Key": new_key}
    pending = await client.get(thread, headers=new)
    assert pending.json()["found"] is True
    assert pending.json()["awaiting_ack"] is True
    stale = await client.post(f"{thread}/ack", json=_signature(plan, "stale-hash"), headers=new)
    assert stale.status_code == 409
    signed = await client.post(f"{thread}/ack", json=_signature(plan), headers=new)
    assert signed.status_code == 200
    assert signed.json()["awaiting_ack"] is False


@pytest.mark.parametrize(
    ("before", "after", "old_key", "new_key"),
    [
        pytest.param(
            Settings(api_keys="alpha:alpha-key-1"),
            Settings(api_keys="alpha:alpha-key-2"),
            "alpha-key-1",
            "alpha-key-2",
            id="named operator",
        ),
        pytest.param(
            Settings(api_key="shared-key-1"),
            Settings(api_key="shared-key-2"),
            "shared-key-1",
            "shared-key-2",
            id="legacy default operator",
        ),
        pytest.param(
            Settings(session_key_secret=_OLD_SECRET),
            Settings(session_key_secret=_NEW_SECRET),
            session_key(_OLD_SECRET, _SESSION),
            session_key(_NEW_SECRET, _SESSION),
            id="session secret",
        ),
    ],
)
async def test_an_open_interrupt_survives_rotation_and_the_old_key_dies(
    app_with_graph: FastAPI,
    configure: Configure,
    before: Settings,
    after: Settings,
    old_key: str,
    new_key: str,
) -> None:
    configure(before)
    async with _client(app_with_graph) as client:
        plan = await _open_interrupt(client, old_key)
        configure(after)
        await _assert_old_key_refused(client, plan, old_key)
        await _assert_new_key_signs(client, plan, new_key)


async def test_rotation_does_not_hand_a_mission_to_another_operator(
    app_with_graph: FastAPI, configure: Configure
) -> None:
    configure(Settings(api_keys="alpha:alpha-key-1,bravo:bravo-key"))
    async with _client(app_with_graph) as client:
        plan = await _open_interrupt(client, "alpha-key-1")
        # alpha's old key handed to bravo: the id owns the mission, not the key.
        configure(Settings(api_keys="alpha:alpha-key-2,bravo:alpha-key-1"))
        thread = f"/api/plan/{plan['thread_id']}"
        peek = await client.get(thread, headers={"X-API-Key": "alpha-key-1"})
        assert peek.json()["found"] is False
        ack = await client.post(
            f"{thread}/ack", json=_signature(plan), headers={"X-API-Key": "alpha-key-1"}
        )
        assert ack.status_code == 404

