"""Two workers seeding one fresh Postgres database at once must both succeed.

The container runs uvicorn with two workers, and each runs the lifespan seed.
On an empty database both used to SELECT, find nothing, and INSERT the same
aircraft; the loser's unique-key violation failed its startup and uvicorn
stopped the whole container (main CI run 40237537525, Compose job). SQLite
serialises writers, so this needs real Postgres: set SUAS_TEST_POSTGRES_URL
(an admin URL; each test creates and drops its own database). CI runs it in
the postgres-integration job.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from sqlalchemy import func, select

from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import AircraftRow, PayloadRow
from suas.db.seed import seed_reference_data

ADMIN_URL = os.environ.get("SUAS_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="needs SUAS_TEST_POSTGRES_URL (real Postgres)"
)

WORKERS = 4
ROUNDS = 5


@pytest.fixture
async def fresh_database_url() -> AsyncIterator[str]:
    name = f"seed_race_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base = ADMIN_URL.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://", 1)
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


async def _seed_once(url: str) -> None:
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as session:
            await seed_reference_data(session)
    finally:
        await engine.dispose()


async def test_concurrent_seeds_on_an_empty_database_all_succeed(
    fresh_database_url: str,
) -> None:
    engine = create_engine(fresh_database_url)
    await create_schema(engine)
    try:
        for _ in range(ROUNDS):
            async with engine.begin() as conn:
                await conn.execute(AircraftRow.__table__.delete())
                await conn.execute(PayloadRow.__table__.delete())
            results = await asyncio.gather(
                *(_seed_once(fresh_database_url) for _ in range(WORKERS)),
                return_exceptions=True,
            )
            assert [r for r in results if isinstance(r, BaseException)] == []
        async with create_session_factory(engine)() as session:
            aircraft = await session.scalar(select(func.count()).select_from(AircraftRow))
            payloads = await session.scalar(select(func.count()).select_from(PayloadRow))
        assert (aircraft, payloads) == (7, 6)
    finally:
        await engine.dispose()
