"""Two workers, one weather cache (#85).

Each worker used to keep its own cache, so worker B fetched again what worker A
had fetched a second earlier: the TTL meant less than it claimed and the
provider saw a request per worker. With ``SUAS_WEATHER_CACHE_SHARED`` the cache
lives in the database every worker already uses. TTL and provenance are
unchanged: a hit inside the TTL is ``cached_fresh``, a miss records whatever
the fetch really was, and an aged reading is ``cached_stale`` only on failure.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from suas.config import Settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.schemas.responses import WeatherSource
from suas.services.weather import (
    DatabaseWeatherCache,
    MemoryWeatherCache,
    WeatherCache,
    WeatherService,
    build_weather_service,
)
from tests.test_shared_rate_limit import postgres_url

__all__ = ["postgres_url"]  # a fixture, used by name

_CURRENT: dict[str, Any] = {
    "temperature_2m": 21.5,
    "wind_speed_10m": 4.0,
    "wind_gusts_10m": 6.0,
    "wind_direction_10m": 180.0,
    "relative_humidity_2m": 55.0,
}
_ROOT = Path(__file__).resolve().parents[2]


class Provider:
    """A scripted weather provider that counts its calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.status = 200
        self.body: Any = {"current": _CURRENT}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(self.status, json=self.body)


def _worker(provider: Provider, cache: WeatherCache) -> WeatherService:
    client = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    return WeatherService(client, "https://weather.invalid/v1", 1, cache_ttl_s=600.0, cache=cache)


async def _two_shared(
    url: str, provider: Provider
) -> tuple[list[WeatherService], list[AsyncEngine]]:
    engines = [create_engine(url) for _ in range(2)]
    await create_schema(engines[0])
    workers = [_worker(provider, DatabaseWeatherCache(create_session_factory(e))) for e in engines]
    return workers, engines


@pytest.fixture
async def shared(tmp_path: Path) -> Any:
    provider = Provider()
    workers, engines = await _two_shared(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}", provider)
    yield provider, workers[0], workers[1]
    for engine in engines:
        await engine.dispose()


async def test_worker_b_serves_cached_fresh_from_worker_a_fetch(shared: Any) -> None:
    provider, a, b = shared

    first = await a.fetch(34.0, -80.0)
    second = await b.fetch(34.001, -80.001)  # same ~1 km cell

    assert (first.source, second.source) == (WeatherSource.LIVE, WeatherSource.CACHED_FRESH)
    assert second.model_dump(exclude={"source"}) == first.model_dump(exclude={"source"})
    assert provider.calls == 1


async def test_the_same_holds_on_postgres(postgres_url: str) -> None:
    provider = Provider()
    workers, engines = await _two_shared(postgres_url, provider)
    try:
        await workers[0].fetch(34.0, -80.0)
        await workers[0].fetch(35.0, -81.0)
        await workers[1].fetch(34.0, -80.0)
        assert (await workers[1].fetch(34.0, -80.0)).source is WeatherSource.CACHED_FRESH
        assert provider.calls == 2
    finally:
        for engine in engines:
            await engine.dispose()


async def test_per_process_caches_fetch_once_per_worker() -> None:
    # The defect, pinned: without a shared cache B cannot see A's reading.
    provider = Provider()
    a, b = _worker(provider, MemoryWeatherCache()), _worker(provider, MemoryWeatherCache())

    await a.fetch(34.0, -80.0)

    assert (await b.fetch(34.0, -80.0)).source is WeatherSource.LIVE
    assert provider.calls == 2


async def _age(cache: WeatherCache, hours: float) -> None:
    key = WeatherService._cache_key(34.0, -80.0)
    reading = await cache.load(key)
    assert reading is not None
    old = datetime.now(UTC) - timedelta(hours=hours)
    await cache.store(key, reading.model_copy(update={"fetched_at": old}))


async def test_a_reading_past_the_ttl_is_fetched_again_as_live(shared: Any) -> None:
    provider, a, b = shared
    await a.fetch(34.0, -80.0)
    await _age(b._cache, hours=2)

    assert (await b.fetch(34.0, -80.0)).source is WeatherSource.LIVE
    assert provider.calls == 2


async def test_a_failed_fetch_after_the_ttl_is_cached_stale_from_the_other_worker(
    shared: Any,
) -> None:
    provider, a, b = shared
    await a.fetch(34.0, -80.0)
    await _age(b._cache, hours=2)
    provider.status = 500

    reading = await b.fetch(34.0, -80.0)

    assert reading.source is WeatherSource.CACHED_STALE
    assert reading.temperature_c == 21.5


@pytest.mark.parametrize(
    ("status", "body", "source"),
    [(500, {}, WeatherSource.FALLBACK), (200, {"current": {}}, WeatherSource.ERROR)],
)
async def test_a_miss_records_what_the_fetch_really_was(
    shared: Any, status: int, body: Any, source: WeatherSource
) -> None:
    provider, a, b = shared
    provider.status, provider.body = status, body

    assert (await a.fetch(34.0, -80.0)).source is source
    # A degraded answer is never cached, so the other worker tries for itself.
    provider.status, provider.body = 200, {"current": _CURRENT}
    assert (await b.fetch(34.0, -80.0)).source is WeatherSource.LIVE


class _Broken:
    def __call__(self) -> Any:
        raise OSError("database unreachable")


async def test_an_unreachable_cache_is_a_miss_not_an_error() -> None:
    # fetch() never raises; a cache it cannot reach just means asking the provider.
    provider = Provider()
    worker = _worker(provider, DatabaseWeatherCache(_Broken()))  # type: ignore[arg-type]

    assert (await worker.fetch(34.0, -80.0)).source is WeatherSource.LIVE
    assert (await worker.fetch(34.0, -80.0)).source is WeatherSource.LIVE


def _built(settings: Settings, session_factory: Any = None) -> Any:
    client = httpx.AsyncClient()
    service = build_weather_service(settings, client, session_factory)
    return service._cache  # type: ignore[union-attr]


def test_sharing_is_opt_in(tmp_path: Path) -> None:
    factory = create_session_factory(create_engine(f"sqlite+aiosqlite:///{tmp_path}/x.db"))
    assert isinstance(_built(Settings(), factory), MemoryWeatherCache)
    assert isinstance(_built(Settings(weather_cache_shared=True), factory), DatabaseWeatherCache)
    with pytest.raises(ValueError, match="session factory"):
        _built(Settings(weather_cache_shared=True))


def test_compose_shares_the_cache_across_its_two_workers() -> None:
    import yaml

    compose = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["backend"]["environment"]
    assert env["SUAS_WEATHER_CACHE_SHARED"] == "${WEATHER_CACHE_SHARED:-true}"
    assert "WEATHER_CACHE_SHARED=true" in (_ROOT / ".env.example").read_text(encoding="utf-8")


def test_the_docs_stop_calling_the_cache_per_process() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    ops = (_ROOT / "docs" / "ops.md").read_text(encoding="utf-8")
    for text in (readme, ops):
        assert "SUAS_WEATHER_CACHE_SHARED" in text
    assert "The cache is per process" not in readme
    assert "A reading fresh in one worker is not fresh in another" not in ops


def test_ci_runs_the_postgres_cache() -> None:
    import yaml

    ci = _ROOT / ".github" / "workflows" / "ci.yml"
    steps = yaml.safe_load(ci.read_text(encoding="utf-8"))["jobs"]["postgres-integration"]["steps"]
    assert any("test_shared_weather_cache.py" in step.get("run", "") for step in steps)
