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
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from suas.errors import SuasError
from suas.schemas.responses import WeatherReading, WeatherSource

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


class WeatherService:
    """Fetches current conditions for a coordinate."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        retry_attempts: int,
        deadline_s: float = 6.0,
        cache_ttl_s: float = 600.0,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._retry_attempts = retry_attempts
        self._deadline_s = deadline_s
        self._cache_ttl_s = cache_ttl_s
        self._cache: dict[tuple[float, float], WeatherReading] = {}

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        """Return current conditions, never raising and never overstating them.

        The whole operation is bounded by one deadline, so retries and per-request
        timeouts cannot compound into a request that outlives the caller's
        patience.
        """
        key = self._cache_key(latitude, longitude)
        cached: WeatherReading | None = self._cache.get(key)
        if cached is not None and self._age_s(cached) <= self._cache_ttl_s:
            return cached.model_copy(update={"source": WeatherSource.CACHED_FRESH})

        try:
            async with asyncio.timeout(self._deadline_s):
                reading = await self._request(latitude, longitude)
        except (TimeoutError, httpx.HTTPError) as exc:
            logger.error("Weather request failed: %s", exc)
            return self._degrade(cached, WeatherSource.FALLBACK, "Live feed unreachable")
        except WeatherPayloadError as exc:
            logger.error("Weather payload unusable: %s", exc)
            return self._degrade(cached, WeatherSource.ERROR, "Live feed returned unusable data")

        self._cache[key] = reading
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
    def _cache_key(latitude: float, longitude: float) -> tuple[float, float]:
        """Return the cache key for a coordinate, rounded to about a kilometre."""
        return (round(latitude, 2), round(longitude, 2))

    @staticmethod
    def _age_s(reading: WeatherReading) -> float:
        """Return how old a cached reading is, treating unknown as infinitely old."""
        if reading.fetched_at is None:
            return math.inf
        return (datetime.now(UTC) - reading.fetched_at).total_seconds()

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
