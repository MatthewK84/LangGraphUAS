"""Tests for the report service fallbacks and idempotent seeding."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings
from suas.db.models import AircraftRow
from suas.db.repository import count_aircraft, get_aircraft, get_payload, list_aircraft
from suas.db.seed import seed_reference_data
from suas.schemas.responses import WeatherReading, WeatherSource
from suas.services.llm import ReportService, _build_prompt, _fallback_report

from .conftest import CALM_WEATHER

_CALC_STUB = {
    "density_altitude_m": 100.0,
    "air_density_ratio": 0.99,
    "energy_required_wh": 120.0,
    "energy_breakdown": {
        "climb_wh": 5.0,
        "cruise_wh": 60.0,
        "hover_wh": 50.0,
        "descent_wh": 5.0,
        "total_wh": 120.0,
    },
    "payload_margin_kg": 1.5,
    "all_up_mass_kg": 6.9,
    "ground_speed_mps": 13.0,
    "effective_hover_power_w": 900.0,
    "battery_check": {
        "energy_required_wh": 120.0,
        "usable_capacity_wh": 400.0,
        "margin_wh": 280.0,
        "reserve_percent": 20.0,
        "temperature_factor": 1.0,
        "is_viable": True,
    },
    "safety_flags": {
        "battery_viable": True,
        "payload_within_limits": True,
        "wind_within_limits": True,
        "gust_within_limits": True,
        "temperature_within_limits": True,
        "cruise_achievable": True,
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


async def test_seed_repairs_drifted_reference_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A corrected figure in the bundled JSON must reach an existing database.

    The previous seed inserted only into an empty table, so a stored row that
    had drifted from the bundled data stayed wrong forever.
    """
    async with session_factory() as session:
        original = await get_aircraft(session, "Skydio_X10D")
        assert original is not None
        row = await session.get(AircraftRow, "Skydio_X10D")
        assert row is not None
        row.battery_wh = 1.0
        row.max_wind_mps = 99.0
        await session.commit()

    async with session_factory() as session:
        drifted = await get_aircraft(session, "Skydio_X10D")
        assert drifted is not None
        assert drifted.battery_wh == 1.0

    async with session_factory() as session:
        await seed_reference_data(session)

    async with session_factory() as session:
        repaired = await get_aircraft(session, "Skydio_X10D")
    assert repaired is not None
    assert repaired.battery_wh == original.battery_wh
    assert repaired.max_wind_mps == original.max_wind_mps


async def test_seed_preserves_operator_added_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Airframes not present in the bundled JSON survive a reconcile."""
    async with session_factory() as session:
        session.add(
            AircraftRow(
                id="Operator_Custom",
                name="Operator Custom",
                weight_kg=3.0,
                max_payload_kg=1.0,
                battery_wh=200.0,
                max_wind_mps=10.0,
                cruise_speed_mps=12.0,
                hover_power_w=300.0,
                cruise_power_w=270.0,
                max_temp_c=40.0,
            )
        )
        await session.commit()

    async with session_factory() as session:
        await seed_reference_data(session)

    async with session_factory() as session:
        survived = await get_aircraft(session, "Operator_Custom")
    assert survived is not None
    assert survived.name == "Operator Custom"


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


def test_bundled_aircraft_have_a_coherent_temperature_envelope() -> None:
    """Every airframe must have a lower limit below its upper limit.

    These are published manufacturer figures, not placeholders, so a nonsensical
    envelope means the reference data has been edited incorrectly.
    """
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent / "suas" / "data"
    records = json.loads((data_dir / "aircraft.json").read_text(encoding="utf-8"))
    assert records
    for aircraft_id, record in records.items():
        assert "min_temp_c" in record, aircraft_id
        assert record["min_temp_c"] < record["max_temp_c"], aircraft_id
        # Sanity bounds: no sUAS in this catalog is rated outside these.
        assert -60.0 < record["min_temp_c"] <= 0.0, aircraft_id
        assert 20.0 <= record["max_temp_c"] < 70.0, aircraft_id
