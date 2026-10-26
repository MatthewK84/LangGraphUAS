"""Boundaries of the in-memory sliding window, on a clock the test controls."""

from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql, sqlite

from suas.api import ratelimit
from suas.api.ratelimit import SlidingWindowLimiter, _retry_after_s
from suas.db.dialect import upsert_insert
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import RateLimitBucketRow
from tests.test_shared_rate_limit import postgres_url

__all__ = ["postgres_url"]  # a fixture, used by name


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(ratelimit.time, "monotonic", fake)
    return fake


def test_a_hit_exactly_one_window_old_has_left_the_window(clock: _Clock) -> None:
    # The shared limiter keeps hits newer than now - window; this one must agree.
    limiter = SlidingWindowLimiter(max_requests=1, window_s=10.0)
    assert limiter.check("a")
    clock.now += 9.999
    assert not limiter.check("a")
    clock.now = 1010.0
    assert limiter.check("a")


def test_tracking_is_kept_up_to_the_client_cap_and_cleared_past_it(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "_MAX_TRACKED_CLIENTS", 2)
    limiter = SlidingWindowLimiter(max_requests=1, window_s=60.0)
    assert limiter.check("a")
    assert limiter.check("b")
    assert not limiter.check("a"), "two clients is within the cap; a keeps its budget"
    assert limiter.check("c")
    assert limiter.check("a"), "a third client clears tracking, so a starts over"


def test_a_client_with_no_hits_has_nothing_to_wait_for(clock: _Clock) -> None:
    assert SlidingWindowLimiter(max_requests=1, window_s=60.0).retry_after_s("never-seen") == 0


@pytest.mark.parametrize(("elapsed", "expected"), [(0.0, 61), (19.5, 41), (59.999, 1)])
def test_retry_after_rounds_up_to_whole_seconds(elapsed: float, expected: int) -> None:
    assert _retry_after_s(1000.0, 1000.0 + elapsed, 60.0) == expected


async def _insert_type(url: str) -> type:
    engine = create_engine(url)
    await create_schema(engine)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return type(upsert_insert(session, RateLimitBucketRow))
    finally:
        await engine.dispose()


async def test_sqlite_gets_the_sqlite_insert(tmp_path: Path) -> None:
    assert await _insert_type(f"sqlite+aiosqlite:///{tmp_path}/d.db") is sqlite.Insert


async def test_postgres_gets_the_postgres_insert(postgres_url: str) -> None:
    # SQLite's ON CONFLICT construct does not compile on Postgres, so the
    # dialect test is load-bearing there.
    assert await _insert_type(postgres_url) is postgresql.Insert
