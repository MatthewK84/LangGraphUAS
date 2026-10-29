"""Datasheet constants after the manufacturer promotion (#74 / #75).

Each promoted constant gets a test so a future edit that reintroduces a
permissive or conflated value fails rather than merely differing from a
changelog entry.
"""

import pytest

from suas.calculations.assessment import assess_mission, is_mission_viable
from suas.reference_data import AIRCRAFT_FILE, load_entries
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.provenance import FieldSource
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading

_PARAMS = MissionParams(
    distance_m=500.0,
    hover_time_s=60.0,
    target_altitude_m=50.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_NO_PAYLOAD = Payload(id="None", name="None", weight_kg=0.0, power_draw_w=0.0)


def _entry(airframe_id: str):
    entries = {entry.id: entry for entry in load_entries(AIRCRAFT_FILE)}
    return entries[airframe_id]


def _weather(temperature_c: float) -> WeatherReading:
    return WeatherReading(
        temperature_c=temperature_c,
        wind_speed_mps=2.0,
        wind_gust_mps=3.0,
        wind_direction=180.0,
        humidity_percent=50.0,
        conditions="calm",
    )


def _astro(pack_min_takeoff_c: float | None) -> Aircraft:
    """Return an Astro-like airframe, with or without the pack procedure."""
    return Aircraft(
        id="TEST_ASTRO",
        name="Astro-like",
        weight_kg=5.593,
        max_payload_kg=3.0,
        battery_wh=314.0,
        max_wind_mps=8.0,
        cruise_speed_mps=14.0,
        hover_power_w=483.1,
        cruise_power_w=434.8,
        max_temp_c=50.0,
        min_temp_c=-20.0,
        pack_min_takeoff_c=pack_min_takeoff_c,
    )


# --- promoted constants -----------------------------------------------------


def test_if1200a_max_temp_matches_manufacturer_sheet() -> None:
    record = _entry("Inspired_Flight_IF1200A").provenance["max_temp_c"]
    assert record.value == 40.0
    assert record.source is FieldSource.DATASHEET
    assert record.source_url


def test_anafi_max_temp_matches_manufacturer_sheet() -> None:
    """Prior circulation of 43/49/50 C is resolved by the 2023-02 product sheet."""
    record = _entry("Parrot_ANAFI_USA").provenance["max_temp_c"]
    assert record.value == 50.0
    assert record.source is FieldSource.DATASHEET
    assert "50" in record.notes


def test_if1200a_battery_is_dual_pack_datasheet_system_energy() -> None:
    record = _entry("Inspired_Flight_IF1200A").provenance["battery_wh"]
    assert record.value == 1420.8
    assert record.source is FieldSource.DATASHEET
    assert "710.4" in record.notes
    assert "two" in record.notes.lower() or "2 x" in record.notes.lower()


def test_alta_x_battery_remains_derived_until_ah_is_on_the_specs_page() -> None:
    record = _entry("Freefly_Alta_X").provenance["battery_wh"]
    assert record.source is FieldSource.DERIVED
    assert "1420.8" in record.notes


def test_alta_x_power_records_the_endurance_discrepancy() -> None:
    """The stored figure does not match the formula its own note names.

    It is conservative, so it stays; the discrepancy is recorded rather than
    silently corrected on the strength of a search summary.
    """
    record = _entry("Freefly_Alta_X").provenance["hover_power_w"]
    assert "20 minutes" in record.notes
    assert "conservative" in record.notes


def test_every_promoted_field_cites_something() -> None:
    airframes = {entry.id: entry for entry in load_entries(AIRCRAFT_FILE)}
    resolved = [
        ("Inspired_Flight_IF1200A", "max_temp_c"),
        ("Inspired_Flight_IF1200A", "battery_wh"),
        ("Parrot_ANAFI_USA", "max_temp_c"),
        ("Parrot_ANAFI_USA", "min_temp_c"),
        ("Freefly_Astro_Max", "pack_min_takeoff_c"),
        ("Freefly_Astro_Max", "max_wind_mps"),
        ("Teal_Golden_Eagle", "max_payload_kg"),
        ("Teal_2", "weight_kg"),
    ]
    for airframe_id, field in resolved:
        record = airframes[airframe_id].provenance[field]
        assert record.source is FieldSource.DATASHEET, f"{airframe_id}.{field}"
        assert record.source_url, f"{airframe_id}.{field} has no URL"
        assert record.retrieved_at, f"{airframe_id}.{field} has no retrieval date"


# --- the pack procedure is its own limit ------------------------------------


def test_astro_carries_the_pack_takeoff_minimum() -> None:
    record = _entry("Freefly_Astro_Max").provenance["pack_min_takeoff_c"]
    assert record.value == 10.0
    assert record.unit == "C"
    assert record.source is FieldSource.DATASHEET


def test_the_pack_limit_is_not_the_airframe_limit() -> None:
    """Collapsing the two would lose a limit, or ground the aircraft at -19 C."""
    entry = _entry("Freefly_Astro_Max")
    assert entry.values["min_temp_c"] == -20.0
    assert entry.values["pack_min_takeoff_c"] == 10.0


@pytest.mark.parametrize("temperature_c", [-5.0, 0.0, 9.9])
def test_cold_ambient_is_a_no_go_for_an_airframe_with_a_pack_procedure(
    temperature_c: float,
) -> None:
    result = assess_mission(
        aircraft=_astro(10.0),
        payload=_NO_PAYLOAD,
        params=_PARAMS,
        weather=_weather(temperature_c),
    )
    assert result.safety_flags.pack_temp_within_takeoff_limits is False
    assert is_mission_viable(result) is False


def test_the_same_cold_is_fine_without_a_documented_procedure() -> None:
    """Absence of a limit is not a limit of zero."""
    result = assess_mission(
        aircraft=_astro(None),
        payload=_NO_PAYLOAD,
        params=_PARAMS,
        weather=_weather(0.0),
    )
    assert result.safety_flags.pack_temp_within_takeoff_limits is True
    assert result.safety_flags.temperature_within_limits is True


def test_warm_enough_clears_the_pack_check() -> None:
    result = assess_mission(
        aircraft=_astro(10.0),
        payload=_NO_PAYLOAD,
        params=_PARAMS,
        weather=_weather(15.0),
    )
    assert result.safety_flags.pack_temp_within_takeoff_limits is True


def test_the_pack_failure_is_named_in_the_reasons() -> None:
    from suas.calculations.assessment import build_assessment

    calculations = assess_mission(
        aircraft=_astro(10.0),
        payload=_NO_PAYLOAD,
        params=_PARAMS,
        weather=_weather(2.0),
    )
    assessment = build_assessment(calculations=calculations, inputs={"t": 2.0})
    assert any("pack" in reason.lower() for reason in assessment.reasons)
