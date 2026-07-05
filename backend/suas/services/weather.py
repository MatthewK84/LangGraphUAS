"""Asynchronous weather service.

Wraps the Open-Meteo API with an explicit timeout, bounded retries, and a
deterministic fallback so a transient outage never blocks a mission plan.
"""

import logging
from typing import Any, Final

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from suas.schemas.responses import WeatherReading

logger: Final[logging.Logger] = logging.getLogger(__name__)

_CURRENT_FIELDS: Final[list[str]] = [
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "relative_humidity_2m",
]
_FALLBACK: Final[WeatherReading] = WeatherReading(
    temperature_c=15.0,
    wind_speed_mps=0.0,
    wind_direction=0.0,
    humidity_percent=50.0,
    conditions="Fallback Defaults",
)


def _parse_current(current: dict[str, Any]) -> WeatherReading:
    """Convert an Open-Meteo ``current`` block into a typed reading."""
    return WeatherReading(
        temperature_c=float(current.get("temperature_2m", _FALLBACK.temperature_c)),
        wind_speed_mps=float(current.get("wind_speed_10m", _FALLBACK.wind_speed_mps)),
        wind_direction=float(current.get("wind_direction_10m", _FALLBACK.wind_direction)),
        humidity_percent=float(current.get("relative_humidity_2m", _FALLBACK.humidity_percent)),
        conditions="Live Meteorological Feed",
    )


class WeatherService:
    """Fetches current conditions for a coordinate."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, retry_attempts: int) -> None:
        self._client = client
        self._base_url = base_url
        self._retry_attempts = retry_attempts

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        """Return current conditions, falling back to defaults on failure."""
        try:
            return await self._request(latitude, longitude)
        except httpx.HTTPError as exc:
            logger.error("Weather request failed after retries: %s", exc)
            return _FALLBACK

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
            body: dict[str, Any] = response.json()
            return _parse_current(body.get("current", {}))

        return await _do()
