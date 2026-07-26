"""Tests for the report service fallbacks and idempotent seeding."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings
from suas.db.repository import count_aircraft, get_aircraft, get_payload, list_aircraft
from suas.db.seed import seed_reference_data
from suas.schemas.responses import WeatherReading, WeatherSource
from suas.services.llm import ReportService, _build_prompt, _fallback_report

from .conftest import CALM_WEATHER

_CALC_STUB = {
    "density_altitude_m": 100.0,
    "energy_required_wh": 120.0,
    "payload_margin_kg": 1.5,
    "battery_check": {
        "energy_required_wh": 120.0,
        "usable_capacity_wh": 400.0,
        "margin_wh": 280.0,
        "reserve_percent": 20.0,
        "is_viable": True,
    },
    "safety_flags": {
        "battery_viable": True,
        "payload_within_limits": True,
        "wind_within_limits": True,
        "temperature_within_limits": True,
    },
}


def _calculations() -> object:
    from suas.schemas.responses import Calculations

    return Calculations.model_validate(_CALC_STUB)


def test_fallback_report_states_decision() -> None:
    assert "GO" in _fallback_report(True)
    assert "NO-GO" in _fallback_report(False)


def test_build_prompt_includes_key_metrics() -> None:
    prompt = _build_prompt(
        is_viable=False,
        aircraft_name="Test Bird",
        weather=CALM_WEATHER,
        calculations=_calculations(),  # type: ignore[arg-type]
    )
    assert "NO-GO" in prompt
    assert "Test Bird" in prompt
    assert "100.0" in prompt


async def test_report_service_falls_back_without_api_key() -> None:
    service = ReportService(Settings(openai_api_key=""))
    report = await service.generate(
        is_viable=True,
        aircraft_name="Test Bird",
        weather=CALM_WEATHER,
        calculations=_calculations(),  # type: ignore[arg-type]
    )
    assert "GO" in report


async def test_seed_is_idempotent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        before = await count_aircraft(session)
        await seed_reference_data(session)
        after = await count_aircraft(session)
    assert before == after
    assert before > 0


async def test_repository_lookup_and_listing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        found = await get_aircraft(session, "Skydio_X10D")
        missing = await get_aircraft(session, "nope")
        payload = await get_payload(session, "None")
        catalog = await list_aircraft(session)
    assert found is not None
    assert found.name
    assert missing is None
    assert payload is not None
    assert len(catalog) > 1


def test_weather_reading_source_defaults_to_live() -> None:
    reading = WeatherReading(
        temperature_c=10.0,
        wind_speed_mps=1.0,
        wind_direction=0.0,
        humidity_percent=50.0,
        conditions="x",
    )
    assert reading.source is WeatherSource.LIVE
    assert reading.is_live is True


@pytest.mark.parametrize("level,expected_json", [("INFO", True), ("DEBUG", False)])
def test_configure_logging_both_modes(level: str, expected_json: bool) -> None:
    import logging

    from suas.logging_config import configure_logging

    configure_logging(level, json_output=expected_json)
    assert logging.getLogger().handlers
