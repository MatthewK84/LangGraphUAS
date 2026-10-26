"""One rate-limit ceiling across workers (#84).

The in-process limiter gives each worker its own budget, so two workers allow
twice the configured requests. With SUAS_RATE_LIMIT_SHARED the budget lives in
the database every worker already shares, so the ceiling is the configured
number whatever the worker count. The per-process limiter stays the default.

Two workers are two limiters over two engines (two connection pools) on one
database file. Set SUAS_TEST_POSTGRES_URL to run the same race on Postgres, as
the postgres-integration CI job does.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from suas.api.ratelimit import DatabaseLimiter, SlidingWindowLimiter, build_limiter
from suas.config import Settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import RateLimitBucketRow

ADMIN_URL = os.environ.get("SUAS_TEST_POSTGRES_URL", "")
LIMIT = 5
WORKERS = 2

Workers = Callable[[int], list[DatabaseLimiter]]


class Clock:
    """A settable wall clock shared by every simulated worker."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


async def _engines(url: str, count: int) -> list[AsyncEngine]:
    engines = [create_engine(url) for _ in range(count)]
    await create_schema(engines[0])
    return engines


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'shared.db'}"


@pytest.fixture
async def postgres_url() -> AsyncIterator[str]:
    if not ADMIN_URL:
        pytest.skip("needs SUAS_TEST_POSTGRES_URL (real Postgres)")
    name = f"rate_limit_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base = ADMIN_URL.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://", 1)
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


async def _workers(url: str, clock: Clock) -> tuple[list[DatabaseLimiter], list[AsyncEngine]]:
    engines = await _engines(url, WORKERS)
    limiters = [
        DatabaseLimiter(create_session_factory(e), LIMIT, 60.0, clock=clock) for e in engines
    ]
    return limiters, engines


async def _race(limiters: list[DatabaseLimiter], requests: int) -> list[int]:
    calls = [limiters[i % len(limiters)].admit("key:alpha") for i in range(requests)]
    return list(await asyncio.gather(*calls))


async def _assert_one_ceiling(url: str) -> None:
    clock = Clock()
    limiters, engines = await _workers(url, clock)
    try:
        waits = await _race(limiters, LIMIT * 3)
        assert waits.count(0) == LIMIT
        assert all(wait > 0 for wait in waits if wait)
    finally:
        for engine in engines:
            await engine.dispose()


async def test_two_workers_share_one_ceiling_on_sqlite(tmp_path: Path) -> None:
    await _assert_one_ceiling(_sqlite_url(tmp_path))


async def test_two_workers_share_one_ceiling_on_postgres(postgres_url: str) -> None:
    await _assert_one_ceiling(postgres_url)


async def test_per_process_limiters_double_the_ceiling() -> None:
    # What the shared limiter fixes: each worker's own budget adds up.
    workers = [SlidingWindowLimiter(LIMIT, 60.0) for _ in range(WORKERS)]
    waits = [await workers[i % WORKERS].admit("key:alpha") for i in range(LIMIT * 3)]
    assert waits.count(0) == LIMIT * WORKERS


async def test_the_window_slides_and_says_when_to_retry(tmp_path: Path) -> None:
    clock = Clock()
    limiters, engines = await _workers(_sqlite_url(tmp_path), clock)
    first, second = limiters
    try:
        assert await first.admit("key:alpha") == 0
        clock.now += 20
        for _ in range(LIMIT - 1):
            assert await second.admit("key:alpha") == 0
        assert await first.admit("key:alpha") == 41  # the first hit leaves at +60
        assert await second.admit("key:bravo") == 0  # buckets are separate
        clock.now += 40
        assert await second.admit("key:alpha") == 0  # the first hit has left
        assert await first.admit("key:alpha") > 0
    finally:
        for engine in engines:
            await engine.dispose()


async def test_the_table_never_holds_a_raw_api_key(tmp_path: Path) -> None:
    limiters, engines = await _workers(_sqlite_url(tmp_path), Clock())
    try:
        await limiters[0].admit("key:ops-secret-value")
        factory: async_sessionmaker[AsyncSession] = create_session_factory(engines[0])
        async with factory() as session:
            buckets = list((await session.scalars(select(RateLimitBucketRow.bucket))).all())
        assert len(buckets) == 1
        assert "ops-secret-value" not in buckets[0]
        assert len(buckets[0]) == 64
    finally:
        for engine in engines:
            await engine.dispose()


async def test_shared_is_opt_in(tmp_path: Path) -> None:
    engine = create_engine(_sqlite_url(tmp_path))
    factory = create_session_factory(engine)
    try:
        assert isinstance(build_limiter(Settings(), factory), SlidingWindowLimiter)
        shared = build_limiter(Settings(rate_limit_shared=True), factory)
        assert isinstance(shared, DatabaseLimiter)
    finally:
        await engine.dispose()


def test_ci_runs_the_postgres_race() -> None:
    import yaml

    ci = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    steps = yaml.safe_load(ci.read_text(encoding="utf-8"))["jobs"]["postgres-integration"]["steps"]
    runs = [s for s in steps if "test_shared_rate_limit.py" in s.get("run", "")]
    assert len(runs) == 1
    assert runs[0]["env"]["SUAS_TEST_POSTGRES_URL"].startswith("postgresql://")
