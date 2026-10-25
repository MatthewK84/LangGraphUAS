"""Startup smoke check.

Boots the application through its real lifespan, which exercises the database
engine, schema creation, seeding, and the Postgres checkpointer, then calls the
ops and catalog endpoints. Exits non-zero on any failure so CI fails loudly.

Run: ``python scripts/smoke_check.py`` against a migrated database.

``--expect-unmigrated`` inverts the readiness checks: pointed at a database
that ``alembic upgrade`` never touched, /ready must answer 503 with
``migrations: pending``. CI runs both directions (#111).
"""

import asyncio
import sys
from typing import Any, Final

import httpx

from suas.main import create_app

_TIMEOUT_S: Final[float] = 30.0


def ready_checks(
    status_code: int, body: dict[str, Any], *, expect_unmigrated: bool
) -> list[tuple[str, bool]]:
    """Name and judge each /ready expectation for the database under test."""
    if expect_unmigrated:
        return [
            ("ready 503 on an unmigrated schema", status_code == 503),
            ("ready migrations pending", body.get("migrations") == "pending"),
        ]
    return [
        ("ready 200", status_code == 200),
        ("ready database ok", body.get("database") == "ok"),
        ("ready migrations ok", body.get("migrations") == "ok"),
        ("ready checkpointer ok", body.get("checkpointer") == "ok"),
    ]


async def _run(*, expect_unmigrated: bool) -> int:
    """Boot the app, probe key endpoints, and return an exit code."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://smoke",
            timeout=_TIMEOUT_S,
        ) as client,
    ):
        health = await client.get("/health")
        ready = await client.get("/ready")
        aircraft = await client.get("/api/aircraft")
        payloads = await client.get("/api/payloads")

    checks: list[tuple[str, bool]] = [
        ("health 200", health.status_code == 200),
        *ready_checks(ready.status_code, ready.json(), expect_unmigrated=expect_unmigrated),
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
    sys.exit(asyncio.run(_run(expect_unmigrated="--expect-unmigrated" in sys.argv[1:])))
