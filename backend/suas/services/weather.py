"""Asynchronous weather service.

Wraps the provider with a hard overall deadline, bounded retries, a short-lived
cache, and strict parsing. The contract this module exists to keep is narrow and
absolute: **a degraded reading must never be indistinguishable from a live one.**

An earlier revision broke that contract in two ways, and both are now tests. A
200 response with an empty or partial ``current`` block produced fallback numbers
tagged ``source: live``, which fed the operational gate a fabricated reading. And
a non-numeric value raised ``ValueError`` past the ``httpx.HTTPError`` handler,
turning a provider's bad day into a 500 from the planning endpoint.
"""

import asyncio
import logging
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Protocol, cast

import httpx
from pydantic import ValidationError
from sqlalchemy import CursorResult, delete, or_, select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from suas.db.dialect import upsert_insert
from suas.db.models import WeatherCacheRow
from suas.errors import SuasError
from suas.schemas.responses import WeatherReading, WeatherSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from suas.config import Settings

logger: Final[logging.Logger] = logging.getLogger(__name__)

_CURRENT_FIELDS: Final[list[str]] = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "relative_humidity_2m",
]

# Gusts are optional: some stations do not report them, and absent gusts are
# meaningfully different from a station that reports no temperature.
_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "relative_humidity_2m",
)

_DEFAULTS: Final[dict[str, float]] = {
    "temperature_c": 15.0,
    "wind_speed_mps": 0.0,
    "wind_gust_mps": 0.0,
    "wind_direction": 0.0,
    "humidity_percent": 50.0,
}


class WeatherPayloadError(SuasError):
    """Raised when the provider answers with something unusable."""


def _degraded_reading(source: WeatherSource, conditions: str) -> WeatherReading:
    """Return a defaults reading, explicitly tagged as not live."""
    return WeatherReading(
        temperature_c=_DEFAULTS["temperature_c"],
        wind_speed_mps=_DEFAULTS["wind_speed_mps"],
        wind_gust_mps=_DEFAULTS["wind_gust_mps"],
        wind_direction=_DEFAULTS["wind_direction"],
        humidity_percent=_DEFAULTS["humidity_percent"],
        conditions=conditions,
        source=source,
        fetched_at=None,
    )


def _coerce(current: dict[str, Any], field: str) -> float:
    """Return one numeric field, or raise WeatherPayloadError.

    Missing, non-numeric, NaN and infinite values are all refused. Substituting a
    default here is what produced fabricated "live" readings before.
    """
    if field not in current or current[field] is None:
        raise WeatherPayloadError(f"Weather payload is missing {field}")
    try:
        value = float(current[field])
    except (TypeError, ValueError) as exc:
        raise WeatherPayloadError(f"Weather field {field} is not a number") from exc
    if not math.isfinite(value):
        raise WeatherPayloadError(f"Weather field {field} is not finite")
    return value


def _parse_current(current: dict[str, Any]) -> WeatherReading:
    """Convert a provider ``current`` block into a typed reading.

    Raises:
        WeatherPayloadError: when any required field is missing or unusable.
    """
    if not current:
        raise WeatherPayloadError("Weather payload has no current block")
    values: dict[str, float] = {field: _coerce(current, field) for field in _REQUIRED_FIELDS}
    gust: float = _DEFAULTS["wind_gust_mps"]
    if current.get("wind_gusts_10m") is not None:
        gust = _coerce(current, "wind_gusts_10m")
    return WeatherReading(
        temperature_c=values["temperature_2m"],
        wind_speed_mps=values["wind_speed_10m"],
        wind_gust_mps=gust,
        wind_direction=values["wind_direction_10m"],
        humidity_percent=values["relative_humidity_2m"],
        # Our own text, never the provider's. A provider-supplied string would be
        # third-party prose heading into a safety brief.
        conditions="Live meteorological feed",
        source=WeatherSource.LIVE,
        fetched_at=datetime.now(UTC),
    )


CacheKey = tuple[float, float]


class WeatherCache(Protocol):
    """Where live readings are kept for reuse inside the TTL."""

    async def load(self, key: CacheKey) -> WeatherReading | None:
        """Return the last live reading for a cell, if any."""
        ...

    async def store(self, key: CacheKey, reading: WeatherReading) -> None:
        """Keep a live reading for a cell."""
        ...


class MemoryWeatherCache:
    """One process's cache: the default, and enough for a single worker."""

    def __init__(self) -> None:
        self._readings: dict[CacheKey, WeatherReading] = {}

    async def load(self, key: CacheKey) -> WeatherReading | None:
        """Return the last live reading for a cell, if any."""
        return self._readings.get(key)

    async def store(self, key: CacheKey, reading: WeatherReading) -> None:
        """Keep a live reading for a cell."""
        self._readings[key] = reading


def _cell(key: CacheKey) -> str:
    """Return the row key for a cell; ``+ 0.0`` folds -0.00 into 0.00 as a dict does."""
    latitude, longitude = key
    return f"{latitude + 0.0:.2f},{longitude + 0.0:.2f}"


_CACHE_FAILURES: Final = (OSError, SQLAlchemyError, ValueError)


class DatabaseWeatherCache:
    """The cache every worker shares, one row per cell in the database (#85).

    Freshness is still judged from the reading's own ``fetched_at`` by the
    service, so the TTL means what it did. A cache the service cannot reach
    is a miss and a lost write, never an exception: ``fetch`` does not raise.
    """

    def __init__(self, session_factory: "async_sessionmaker[AsyncSession]") -> None:
        self._session_factory = session_factory

    async def load(self, key: CacheKey) -> WeatherReading | None:
        """Return the last live reading any worker stored for a cell."""
        query = select(WeatherCacheRow.reading).where(WeatherCacheRow.cell == _cell(key))
        try:
            async with self._session_factory() as session:
                stored: dict[str, Any] | None = await session.scalar(query)
            return None if stored is None else WeatherReading.model_validate(stored)
        except _CACHE_FAILURES as exc:
            logger.warning("Shared weather cache unreadable, treating as a miss: %s", exc)
            return None

    async def store(self, key: CacheKey, reading: WeatherReading) -> None:
        """Keep a live reading where every worker can see it."""
        try:
            async with self._session_factory() as session, session.begin():
                insert = upsert_insert(session, WeatherCacheRow).values(
                    cell=_cell(key), reading=reading.model_dump(mode="json")
                )
                await session.execute(
                    insert.on_conflict_do_update(
                        index_elements=["cell"], set_={"reading": insert.excluded.reading}
                    )
                )
        except _CACHE_FAILURES as exc:
            logger.warning("Shared weather cache unwritable, reading not kept: %s", exc)


def _utcnow() -> datetime:
    """Return the current time, aware, for judging a reading's age."""
    return datetime.now(UTC)


def _age_s(fetched_at: datetime | None, now: datetime) -> float:
    """Return how old a reading is, treating unknown as infinitely old."""
    if fetched_at is None:
        return math.inf
    return (now - fetched_at).total_seconds()


_MAX_CELLS_PER_PRUNE: Final[int] = 1000


def _stored_fetched_at(stored: dict[str, Any]) -> datetime | None:
    """Return a stored reading's fetch time; an unreadable row has none."""
    try:
        return WeatherReading.model_validate(stored).fetched_at
    except ValidationError:
        return None


def _expired_cells(
    rows: Sequence[WeatherCacheRow], max_age_s: float, now: datetime
) -> list[WeatherCacheRow]:
    """Return the rows whose reading is past the max age."""
    return [row for row in rows if _age_s(_stored_fetched_at(row.reading), now) > max_age_s]


def _unchanged(rows: list[WeatherCacheRow]) -> Any:
    """Match these rows only while they still hold the reading that was judged.

    SQLite has no row locks, so another worker may store a live reading between
    the read and the delete; matching on the stored ``fetched_at`` misses it.
    """
    fetched_at = WeatherCacheRow.reading["fetched_at"].as_string()
    dated = [
        (row.cell, str(row.reading["fetched_at"])) for row in rows if row.reading.get("fetched_at")
    ]
    undated = [row.cell for row in rows if not row.reading.get("fetched_at")]
    return or_(
        tuple_(WeatherCacheRow.cell, fetched_at).in_(dated),
        WeatherCacheRow.cell.in_(undated) & fetched_at.is_(None),
    )


async def prune_stale_weather(
    session_factory: "async_sessionmaker[AsyncSession]",
    max_age_s: float,
    clock: Callable[[], datetime] = _utcnow,
) -> int:
    """Delete shared readings past the stale max age; return how many.

    Such a row is never served (an outage answers as if it were missing), so
    pruning changes no answer. Rows are paged in key order and read under
    ``FOR UPDATE SKIP LOCKED``: a row mid-store is left for the next pass.
    """
    pruned, after = 0, ""
    while True:
        async with session_factory() as session, session.begin():
            page = (
                select(WeatherCacheRow)
                .where(WeatherCacheRow.cell > after)
                .order_by(WeatherCacheRow.cell)
                .limit(_MAX_CELLS_PER_PRUNE)
                .with_for_update(skip_locked=True)
            )
            rows = list((await session.execute(page)).scalars())
            if not rows:
                return pruned
            expired = _expired_cells(rows, max_age_s, clock())
            if expired:
                deleted = await session.execute(delete(WeatherCacheRow).where(_unchanged(expired)))
                pruned += cast("CursorResult[Any]", deleted).rowcount
            after = rows[-1].cell


class WeatherService:
    """Fetches current conditions for a coordinate."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        retry_attempts: int,
        deadline_s: float = 6.0,
        cache_ttl_s: float = 600.0,
        cache: WeatherCache | None = None,
        stale_max_age_s: float = 10800.0,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._retry_attempts = retry_attempts
        self._deadline_s = deadline_s
        self._cache_ttl_s = cache_ttl_s
        self._stale_max_age_s = stale_max_age_s
        self._clock = clock
        self._cache: WeatherCache = MemoryWeatherCache() if cache is None else cache

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        """Return current conditions, never raising and never overstating them.

        The whole operation is bounded by one deadline, so retries and per-request
        timeouts cannot compound into a request that outlives the caller's
        patience.
        """
        key = self._cache_key(latitude, longitude)
        cached: WeatherReading | None = await self._cache.load(key)
        if cached is not None and self._age_s(cached) <= self._cache_ttl_s:
            return cached.model_copy(update={"source": WeatherSource.CACHED_FRESH})
        if cached is not None and self._age_s(cached) > self._stale_max_age_s:
            cached = None  # too old to stand in for the weather now: as if missing

        try:
            async with asyncio.timeout(self._deadline_s):
                reading = await self._request(latitude, longitude)
        except (TimeoutError, httpx.HTTPError) as exc:
            logger.error("Weather request failed: %s", exc)
            return self._degrade(cached, WeatherSource.FALLBACK, "Live feed unreachable")
        except WeatherPayloadError as exc:
            logger.error("Weather payload unusable: %s", exc)
            return self._degrade(cached, WeatherSource.ERROR, "Live feed returned unusable data")

        await self._cache.store(key, reading)
        return reading

    def _degrade(
        self,
        cached: WeatherReading | None,
        source: WeatherSource,
        conditions: str,
    ) -> WeatherReading:
        """Return the best degraded answer available, correctly labelled."""
        if cached is not None:
            return cached.model_copy(
                update={
                    "source": WeatherSource.CACHED_STALE,
                    "conditions": f"{conditions}; using a cached reading",
                }
            )
        return _degraded_reading(source, conditions)

    @staticmethod
    def _cache_key(latitude: float, longitude: float) -> CacheKey:
        """Return the cache key for a coordinate, rounded to about a kilometre."""
        return (round(latitude, 2), round(longitude, 2))

    def _age_s(self, reading: WeatherReading) -> float:
        """Return how old a cached reading is, treating unknown as infinitely old."""
        return _age_s(reading.fetched_at, self._clock())

    async def _request(self, latitude: float, longitude: float) -> WeatherReading:
        """Perform the retried HTTP request and parse the result."""
        attempts: int = self._retry_attempts

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.5, max=4.0),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        )
        async def _do() -> WeatherReading:
            params: dict[str, Any] = {
                "latitude": latitude,
                "longitude": longitude,
                "current": _CURRENT_FIELDS,
                "wind_speed_unit": "ms",
                "timezone": "auto",
            }
            response = await self._client.get(self._base_url, params=params)
            response.raise_for_status()
            try:
                body: dict[str, Any] = response.json()
            except ValueError as exc:
                raise WeatherPayloadError("Weather response was not JSON") from exc
            return _parse_current(body.get("current", {}))

        return await _do()


class WeatherProvider(Protocol):
    """Anything the graph can ask for current conditions."""

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        """Return current conditions for a coordinate."""
        ...


_FIXTURE_CONDITIONS: Final[str] = "demo fixture: calm, clear (not observed weather)"


class FixtureWeather:
    """Demo mode's weather: one calm reading, tagged ``fixture``, with no network.

    ``FIXTURE`` is not operational grade, so the gate adds WEATHER_NOT_LIVE and
    every demo plan comes back advisory, whatever the caller asked for.
    """

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        """Return the fixture reading for any coordinate."""
        _ = (latitude, longitude)
        return _degraded_reading(WeatherSource.FIXTURE, _FIXTURE_CONDITIONS)


def _build_cache(
    settings: "Settings", session_factory: "async_sessionmaker[AsyncSession] | None"
) -> WeatherCache:
    """Return the shared cache when configured, else this process's own."""
    if not settings.weather_cache_shared:
        return MemoryWeatherCache()
    if session_factory is None:
        raise ValueError("SUAS_WEATHER_CACHE_SHARED needs the database session factory")
    return DatabaseWeatherCache(session_factory)


def build_weather_service(
    settings: "Settings",
    client: httpx.AsyncClient,
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
) -> WeatherProvider:
    """Return the fixture provider in demo mode, the live provider otherwise."""
    if settings.demo_mode:
        logger.warning("DEMO MODE: fixture weather, every plan is advisory")
        return FixtureWeather()
    return WeatherService(
        client=client,
        base_url=settings.weather_base_url,
        retry_attempts=settings.weather_retry_attempts,
        deadline_s=settings.weather_deadline_s,
        cache_ttl_s=settings.weather_cache_ttl_s,
        stale_max_age_s=settings.weather_stale_max_age_s,
        cache=_build_cache(settings, session_factory),
    )
