"""A stale weather reading has a maximum age, and the cache is pruned past it.

A reading past ``SUAS_WEATHER_CACHE_TTL_S`` used to be the ``cached_stale``
answer to a provider outage however old it was: a reading from last week was
served as the weather now. Past ``SUAS_WEATHER_STALE_MAX_AGE_S`` the service
now answers as if nothing were cached, the same ``fallback`` or ``error``
reading a cold cache gets, and the retention pass deletes such rows from the
shared cache. Both are judged from the reading's own ``fetched_at``.
"""

import asyncio
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import suas.services.weather as weather
from suas.config import Settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import WeatherCacheRow
from suas.main import _housekeep, _prune_weather_cache
from suas.schemas.responses import WeatherReading, WeatherSource
from suas.services.weather import (
    DatabaseWeatherCache,
    MemoryWeatherCache,
    WeatherCache,
    WeatherService,
    build_weather_service,
    prune_stale_weather,
)
from tests.test_shared_rate_limit import postgres_url

__all__ = ["postgres_url"]  # a fixture, used by name

_NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
_TTL_S = 600.0
_MAX_AGE_S = 10800.0
_KEY = (34.0, -80.0)
_CURRENT: dict[str, Any] = {
    "temperature_2m": 21.5,
    "wind_speed_10m": 4.0,
    "wind_gusts_10m": 6.0,
    "wind_direction_10m": 180.0,
    "relative_humidity_2m": 55.0,
}
_ROOT = Path(__file__).resolve().parents[2]


def _clock() -> datetime:
    return _NOW


def _reading(age_s: float | None) -> WeatherReading:
    return WeatherReading(
        temperature_c=21.5,
        wind_speed_mps=4.0,
        wind_gust_mps=6.0,
        wind_direction=180.0,
        humidity_percent=55.0,
        conditions="observed",
        source=WeatherSource.LIVE,
        fetched_at=None if age_s is None else _NOW - timedelta(seconds=age_s),
    )


def _service(status: int, body: Any, cache: WeatherCache) -> WeatherService:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    return WeatherService(
        client,
        "https://weather.invalid/v1",
        1,
        cache_ttl_s=_TTL_S,
        stale_max_age_s=_MAX_AGE_S,
        cache=cache,
        clock=_clock,
    )


_OUTAGES = pytest.mark.parametrize(
    ("status", "body"), [(500, {}), (200, {"current": {}})], ids=["unreachable", "unusable"]
)


async def _outage(status: int, body: Any, cached_age_s: float | None) -> WeatherReading:
    cache = MemoryWeatherCache()
    if cached_age_s is not None:
        await cache.store(_KEY, _reading(cached_age_s))
    return await _service(status, body, cache).fetch(*_KEY)


# --- the service --------------------------------------------------------------


@_OUTAGES
@pytest.mark.parametrize("age_s", [_TTL_S + 1.0, _MAX_AGE_S - 1.0, _MAX_AGE_S])
async def test_an_outage_within_the_max_age_is_cached_stale(
    status: int, body: Any, age_s: float
) -> None:
    reading = await _outage(status, body, age_s)

    assert reading.source is WeatherSource.CACHED_STALE
    assert reading.temperature_c == 21.5


@_OUTAGES
@pytest.mark.parametrize("age_s", [_MAX_AGE_S + 0.001, 7 * 86400.0])
async def test_an_outage_past_the_max_age_answers_as_an_empty_cache(
    status: int, body: Any, age_s: float
) -> None:
    reading = await _outage(status, body, age_s)

    assert reading == await _outage(status, body, None)
    assert reading.source in (WeatherSource.FALLBACK, WeatherSource.ERROR)
    assert reading.fetched_at is None


async def test_a_reading_with_no_fetch_time_is_past_any_max_age() -> None:
    assert (await _outage(500, {}, None)) == await _outage_with(_reading(None))


async def _outage_with(stored: WeatherReading) -> WeatherReading:
    cache = MemoryWeatherCache()
    await cache.store(_KEY, stored)
    return await _service(500, {}, cache).fetch(*_KEY)


async def test_a_live_fetch_still_replaces_an_expired_reading() -> None:
    cache = MemoryWeatherCache()
    await cache.store(_KEY, _reading(7 * 86400.0))

    assert (await _service(200, {"current": _CURRENT}, cache).fetch(*_KEY)).source is (
        WeatherSource.LIVE
    )


async def test_the_shared_cache_honours_the_max_age_too(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}")
    await create_schema(engine)
    cache = DatabaseWeatherCache(create_session_factory(engine))
    try:
        await cache.store(_KEY, _reading(_MAX_AGE_S + 1.0))
        reading = await _service(500, {}, cache).fetch(*_KEY)
    finally:
        await engine.dispose()

    assert reading.source is WeatherSource.FALLBACK


# --- the setting --------------------------------------------------------------


def test_the_max_age_defaults_to_three_hours_and_is_built_in() -> None:
    settings = Settings()
    assert settings.weather_stale_max_age_s == _MAX_AGE_S
    service = build_weather_service(settings, httpx.AsyncClient())
    assert service._stale_max_age_s == _MAX_AGE_S  # type: ignore[union-attr]
    shorter = build_weather_service(Settings(weather_stale_max_age_s=900.0), httpx.AsyncClient())
    assert shorter._stale_max_age_s == 900.0  # type: ignore[union-attr]


@pytest.mark.parametrize("max_age_s", [0.0, -1.0, _TTL_S - 1.0])
def test_the_max_age_cannot_undercut_the_ttl(max_age_s: float) -> None:
    with pytest.raises(ValidationError):
        Settings(weather_stale_max_age_s=max_age_s)


def test_the_max_age_may_equal_the_ttl() -> None:
    assert Settings(weather_stale_max_age_s=_TTL_S).weather_stale_max_age_s == _TTL_S


# --- pruning the shared cache -------------------------------------------------


@pytest.fixture
async def factory(tmp_path: Path) -> Any:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    await create_schema(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _rows(factory: async_sessionmaker[AsyncSession], **ages: float | None) -> None:
    async with factory() as session:
        session.add_all(
            WeatherCacheRow(cell=cell, reading=_reading(age).model_dump(mode="json"))
            for cell, age in ages.items()
        )
        await session.commit()


async def _cells_left(factory: async_sessionmaker[AsyncSession]) -> set[str]:
    async with factory() as session:
        return set((await session.execute(select(WeatherCacheRow.cell))).scalars())


def _prune(factory: async_sessionmaker[AsyncSession]) -> Any:
    return prune_stale_weather(factory, _MAX_AGE_S, clock=_clock)


async def test_only_rows_past_the_max_age_are_pruned(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _rows(
        factory,
        fresh=10.0,
        stale=_TTL_S + 60.0,
        edge=_MAX_AGE_S,  # exactly the max age: still served, so kept
        expired=_MAX_AGE_S + 0.001,
        ancient=30 * 86400.0,
        undated=None,
    )

    assert await _prune(factory) == 3
    assert await _cells_left(factory) == {"fresh", "stale", "edge"}


async def test_pruning_pages_through_more_rows_than_one_batch(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    # The first rows in key order are fresh; an unordered single batch of
    # them would never reach the expired rows behind.
    await _rows(factory, **{f"a{i:04d}": 10.0 for i in range(1001)})
    await _rows(factory, **{f"b{i:04d}": _MAX_AGE_S * 2 for i in range(5)})

    assert await _prune(factory) == 5
    assert len(await _cells_left(factory)) == 1001


async def test_a_reading_refreshed_mid_prune_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SQLite has no row locks: another worker may store a live reading after
    # the prune read the row and before it deletes it. The delete must miss it.
    path = tmp_path / "race.db"
    engine = create_engine(f"sqlite+aiosqlite:///{path}")
    await create_schema(engine)
    factory = create_session_factory(engine)
    await _rows(factory, cell=_MAX_AGE_S * 2)
    real = weather._expired_cells

    def judge_then_refresh(rows: Any, max_age_s: float, now: datetime) -> Any:
        expired = real(rows, max_age_s, now)
        with sqlite3.connect(path) as other_worker:
            fresh = json.dumps(_reading(1.0).model_dump(mode="json"))
            other_worker.execute("UPDATE weather_cache SET reading = ?", (fresh,))
        return expired

    monkeypatch.setattr(weather, "_expired_cells", judge_then_refresh)
    try:
        assert await _prune(factory) == 0
        assert await _cells_left(factory) == {"cell"}
    finally:
        await engine.dispose()


async def _two_workers(url: str) -> tuple[list[Any], list[AsyncEngine]]:
    engines = [create_engine(url) for _ in range(2)]
    await create_schema(engines[0])
    async with create_session_factory(engines[0])() as session:
        await session.execute(WeatherCacheRow.__table__.delete())
        await session.commit()
    return [create_session_factory(e) for e in engines], engines


async def _assert_two_workers_prune_each_row_once(url: str) -> None:
    factories, engines = await _two_workers(url)
    try:
        await _rows(factories[0], **{f"old{i}": _MAX_AGE_S * 2 for i in range(20)}, fresh=1.0)
        counts = await asyncio.gather(*(_prune(f) for f in factories))
        assert sum(counts) == 20
        assert await _cells_left(factories[0]) == {"fresh"}
    finally:
        for engine in engines:
            await engine.dispose()


async def test_two_workers_prune_each_row_once_on_sqlite(tmp_path: Path) -> None:
    await _assert_two_workers_prune_each_row_once(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")


async def test_two_workers_prune_each_row_once_on_postgres(postgres_url: str) -> None:
    await _assert_two_workers_prune_each_row_once(postgres_url)


async def test_a_row_mid_store_is_skipped_not_waited_on(postgres_url: str) -> None:
    factories, engines = await _two_workers(postgres_url)
    try:
        await _rows(factories[0], busy=_MAX_AGE_S * 2, idle=_MAX_AGE_S * 2)
        async with factories[0]() as storing, storing.begin():
            locked = select(WeatherCacheRow).where(WeatherCacheRow.cell == "busy")
            row = (await storing.execute(locked.with_for_update())).scalar_one()
            pruned = await asyncio.wait_for(_prune(factories[1]), timeout=5.0)
            row.reading = _reading(1.0).model_dump(mode="json")
        assert pruned == 1
        assert await _cells_left(factories[1]) == {"busy"}
    finally:
        for engine in engines:
            await engine.dispose()


async def test_a_store_survives_its_row_being_pruned(postgres_url: str) -> None:
    factories, engines = await _two_workers(postgres_url)
    try:
        cache = DatabaseWeatherCache(factories[1])
        await cache.store(_KEY, _reading(_MAX_AGE_S * 2))
        async with factories[0]() as pruning, pruning.begin():
            locked = select(WeatherCacheRow).with_for_update()
            row = (await pruning.execute(locked)).scalar_one()
            store = asyncio.create_task(cache.store(_KEY, _reading(1.0)))
            await asyncio.sleep(0.3)
            await pruning.delete(row)
        await asyncio.wait_for(store, timeout=5.0)
        kept = await cache.load(_KEY)
        assert kept is not None and kept.fetched_at == _NOW - timedelta(seconds=1.0)
    finally:
        for engine in engines:
            await engine.dispose()


# --- the retention pass -------------------------------------------------------


class _DownDatabase:
    def __call__(self) -> Any:
        raise RuntimeError("database is down")


async def test_a_failed_weather_prune_is_logged_and_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="suas.main"):
        result = await _prune_weather_cache(_DownDatabase(), Settings())  # type: ignore[arg-type]

    assert result is None
    assert "Weather cache pruning pass failed: database is down" in caplog.text


async def test_the_retention_pass_prunes_expired_weather_and_says_so(
    factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    await _rows(factory, fresh=1.0, gone=30 * 86400.0)
    with caplog.at_level(logging.INFO, logger="suas.main"):
        await _housekeep(factory, InMemorySaver(), Settings())
        await _housekeep(factory, InMemorySaver(), Settings())

    assert await _cells_left(factory) == {"fresh"}
    assert caplog.text.count("Pruned 1 expired weather readings") == 1


# --- docs and CI --------------------------------------------------------------


def _text(relative: str) -> str:
    return re.sub(r"\s+", " ", (_ROOT / relative).read_text(encoding="utf-8"))


def test_the_docs_describe_the_max_age() -> None:
    for doc in ("README.md", "docs/ops.md", "docs/threat-model.md"):
        assert "SUAS_WEATHER_STALE_MAX_AGE_S" in _text(doc), doc
    assert "Leaves `weather_cache` alone" not in _text("docs/ops.md")


def test_ci_runs_the_postgres_prune() -> None:
    import yaml

    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["postgres-integration"]["steps"]
    runs = " ".join(str(step.get("run", "")) for step in steps)
    assert "tests/test_weather_stale_max_age.py" in runs
