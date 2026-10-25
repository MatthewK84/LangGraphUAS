"""Workers starting against one fresh Postgres database at once must all succeed.

The container runs uvicorn with two workers, and each runs the whole lifespan:
create_schema, the reference seed, and the checkpointer's schema setup. Each
of those is check-then-write, so on an empty database concurrent workers used
to race, and the loser's unique-key violation failed its startup and uvicorn
stopped the whole container:

- seed: duplicate aircraft key (main CI run 40237537525, fixed in #160);
- checkpointer setup: duplicate ``checkpoint_migrations`` version (main CI run
  40240790618).

SQLite serialises writers, so this needs real Postgres: set
SUAS_TEST_POSTGRES_URL (an admin URL; each test creates and drops its own
database). CI runs it in the postgres-integration job.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select, text

from suas.config import Settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import AircraftRow, Base, PayloadRow
from suas.db.seed import seed_reference_data
from suas.graph.checkpointer import build_checkpointer

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


_CHECKPOINT_TABLES = "checkpoint_migrations, checkpoints, checkpoint_blobs, checkpoint_writes"


async def _start_checkpointer_once(url: str) -> None:
    async with build_checkpointer(Settings(database_url=url)):
        pass


async def _gather_all_succeed(*calls: Any) -> None:
    results = await asyncio.gather(*calls, return_exceptions=True)
    assert [r for r in results if isinstance(r, BaseException)] == []


async def test_concurrent_checkpointer_setup_on_an_empty_database_all_succeed(
    fresh_database_url: str,
) -> None:
    engine = create_engine(fresh_database_url)
    try:
        for _ in range(ROUNDS):
            async with engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {_CHECKPOINT_TABLES}"))
            await _gather_all_succeed(
                *(_start_checkpointer_once(fresh_database_url) for _ in range(WORKERS))
            )
        async with engine.connect() as conn:
            versions = await conn.scalar(text("SELECT count(*) FROM checkpoint_migrations"))
        assert versions == len(AsyncPostgresSaver.MIGRATIONS)
    finally:
        await engine.dispose()


async def _create_schema_once(url: str) -> None:
    engine = create_engine(url)
    try:
        await create_schema(engine)
    finally:
        await engine.dispose()


async def test_concurrent_create_schema_on_an_empty_database_all_succeed(
    fresh_database_url: str,
) -> None:
    engine = create_engine(fresh_database_url)
    try:
        for _ in range(ROUNDS):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await _gather_all_succeed(
                *(_create_schema_once(fresh_database_url) for _ in range(WORKERS))
            )
    finally:
        await engine.dispose()
