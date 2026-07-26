"""Tests for the weather service, including retry and fallback behavior."""

import httpx

from suas.schemas.responses import WeatherSource
from suas.services.weather import WeatherService

_BASE = "https://weather.test/v1/forecast"

_PAYLOAD = {
    "current": {
        "temperature_2m": 21.5,
        "wind_speed_10m": 4.2,
        "wind_direction_10m": 210,
        "relative_humidity_2m": 55,
    }
}


async def test_weather_parses_live_reading() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_PAYLOAD))
    async with httpx.AsyncClient(transport=transport) as client:
        service = WeatherService(client=client, base_url=_BASE, retry_attempts=1)
        reading = await service.fetch(34.0, -80.0)
    assert reading.temperature_c == 21.5
    assert reading.wind_speed_mps == 4.2
    assert reading.source is WeatherSource.LIVE
    assert reading.is_live is True


async def test_weather_falls_back_after_persistent_failure() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        service = WeatherService(client=client, base_url=_BASE, retry_attempts=2)
        reading = await service.fetch(34.0, -80.0)
    assert reading.source is WeatherSource.FALLBACK
    assert reading.is_live is False


async def test_weather_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json=_PAYLOAD)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = WeatherService(client=client, base_url=_BASE, retry_attempts=3)
        reading = await service.fetch(34.0, -80.0)
    assert calls["n"] == 2
    assert reading.source is WeatherSource.LIVE


async def test_weather_missing_fields_use_defaults() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"current": {}}))
    async with httpx.AsyncClient(transport=transport) as client:
        service = WeatherService(client=client, base_url=_BASE, retry_attempts=1)
        reading = await service.fetch(34.0, -80.0)
    assert reading.temperature_c == 15.0
