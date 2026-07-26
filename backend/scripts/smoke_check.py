"""Startup smoke check.

Boots the application through its real lifespan, which exercises the database
engine, schema creation, seeding, and the Postgres checkpointer, then calls the
ops and catalog endpoints. Exits non-zero on any failure so CI fails loudly.

Run: ``python scripts/smoke_check.py``
"""

import asyncio
import sys
from typing import Final

import httpx

from suas.main import create_app

_TIMEOUT_S: Final[float] = 30.0


async def _run() -> int:
    """Boot the app, probe key endpoints, and return an exit code."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport,
        base_url="http://smoke",
        timeout=_TIMEOUT_S,
    ) as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
        aircraft = await client.get("/api/aircraft")
        payloads = await client.get("/api/payloads")

    checks: list[tuple[str, bool]] = [
        ("health 200", health.status_code == 200),
        ("ready 200", ready.status_code == 200),
        ("ready database ok", ready.json().get("database") == "ok"),
        ("aircraft catalog non-empty", len(aircraft.json()) > 0),
        ("payload catalog non-empty", len(payloads.json()) > 0),
    ]
    failures: list[str] = [name for name, passed in checks if not passed]
    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if failures:
        print(f"Smoke check failed: {', '.join(failures)}")
        return 1
    print(f"Smoke check passed. Seeded {len(aircraft.json())} aircraft.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
