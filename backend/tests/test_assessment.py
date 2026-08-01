"""Unit tests for the pure mission assessment aggregator."""

from suas.calculations.assessment import assess_mission, is_mission_viable
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading

_AIRCRAFT = Aircraft(
    id="TEST",
    name="Test Bird",
    weight_kg=6.0,
    max_payload_kg=2.7,
    battery_wh=588.0,
    max_wind_mps=12.0,
    cruise_speed_mps=15.0,
    hover_power_w=820.0,
    cruise_power_w=690.0,
    max_temp_c=50.0,
)
_PAYLOAD = Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0)
_PARAMS = MissionParams(
    distance_m=1000.0,
    hover_time_s=60.0,
    target_altitude_m=120.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_CALM = WeatherReading(
    temperature_c=20.0,
    wind_speed_mps=3.0,
    wind_direction=90.0,
    humidity_percent=40.0,
    conditions="calm",
)


def test_assessment_viable_in_calm_conditions() -> None:
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    assert is_mission_viable(result) is True
    assert result.safety_flags.wind_within_limits is True


def test_assessment_computes_expected_magnitudes() -> None:
    """Pin the numbers, not just the flags.

    Cruise: 1000 m / 15 m/s = 66.67 s at (690 + 28) W. Hover: 60 s at
    (820 + 28) W. Total = (50880 + 47866.7) J / 3600 = 27.43 Wh.
    Payload margin = 2.7 - 0.9 = 1.8 kg.
    """
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    assert result.energy_required_wh == 27.43
    assert result.payload_margin_kg == 1.8
    assert result.battery_check.usable_capacity_wh == 470.4
    assert result.battery_check.margin_wh == 442.97


def test_assessment_uses_target_altitude_for_density_altitude() -> None:
    """The target altitude is a live input, not a decorative form field.

    Under a standard lapse rate, planning 120 m higher raises density altitude
    by exactly 120 m. If this regresses, the field has gone dead again.
    """
    at_surface = _PARAMS.model_copy(update={"target_altitude_m": 0.0})
    surface_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=at_surface, weather=_CALM
    )
    aloft_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM
    )
    assert aloft_result.density_altitude_m - surface_result.density_altitude_m == 120.0


def test_assessment_density_altitude_reflects_warm_day_at_sea_level() -> None:
    """20 C at sea level, planned at 120 m AGL: 36.21 * 5 + 120 = 301.05 m."""
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    assert result.density_altitude_m == 301.05


def test_assessment_flags_high_wind() -> None:
    gusty = _CALM.model_copy(update={"wind_speed_mps": 20.0})
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=gusty)
    assert result.safety_flags.wind_within_limits is False
    assert is_mission_viable(result) is False


def test_assessment_flags_overweight_payload() -> None:
    heavy = Payload(id="H", name="Heavy", weight_kg=5.0, power_draw_w=10.0)
    result = assess_mission(aircraft=_AIRCRAFT, payload=heavy, params=_PARAMS, weather=_CALM)
    assert result.safety_flags.payload_within_limits is False
    assert result.payload_margin_kg < 0.0
