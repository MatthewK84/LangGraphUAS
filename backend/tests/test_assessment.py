"""Unit tests for the pure mission assessment aggregator.

The model corrects power for mass and air density, charges climb and descent,
penalises cruise for headwind, and derates cold battery capacity. Each of those
was previously absent, and every omission biased the result toward GO, so these
tests assert direction as well as magnitude.
"""

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
    min_temp_c=-20.0,
)
_PAYLOAD = Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0)
_NO_PAYLOAD = Payload(id="None", name="None", weight_kg=0.0, power_draw_w=0.0)
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
    wind_gust_mps=4.0,
    wind_direction=90.0,
    humidity_percent=40.0,
    conditions="calm",
)


def test_assessment_viable_in_calm_conditions() -> None:
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    assert is_mission_viable(result) is True
    assert result.safety_flags.wind_within_limits is True
    assert result.safety_flags.gust_within_limits is True
    assert result.safety_flags.cruise_achievable is True


def test_assessment_computes_expected_magnitudes() -> None:
    """Pin the numbers, not just the flags.

    Density altitude at 120 m AGL and 20 C is 301.05 m, giving a density ratio
    of 0.9714. All-up mass 6.9 kg against a 6.0 kg reference is a mass ratio of
    1.15, so hover power scales by 1.15^1.5 / sqrt(0.9714) to 1026.03 W.
    Ground speed is 15 - 3 = 12 m/s against the worst-case headwind.
    """
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    assert result.density_altitude_m == 301.05
    assert result.air_density_ratio == 0.9714
    assert result.all_up_mass_kg == 6.9
    assert result.ground_speed_mps == 12.0
    assert result.effective_hover_power_w == 1026.03
    assert result.energy_breakdown.climb_wh == 15.47
    assert result.energy_breakdown.cruise_wh == 20.63
    assert result.energy_breakdown.hover_wh == 17.57
    assert result.energy_breakdown.descent_wh == 11.71
    assert result.energy_required_wh == 65.38
    assert result.battery_check.usable_capacity_wh == 470.4
    assert result.battery_check.margin_wh == 405.02


def test_energy_breakdown_sums_to_total() -> None:
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    parts = result.energy_breakdown
    assert round(parts.climb_wh + parts.cruise_wh + parts.hover_wh + parts.descent_wh, 2) == (
        parts.total_wh
    )


def test_payload_mass_increases_energy_demand() -> None:
    """Carrying mass must cost energy, not just consume payload margin.

    Previously only the payload's electrical draw counted, so hanging mass on
    the airframe was free in the energy budget.
    """
    heavy = Payload(id="H", name="Heavy", weight_kg=2.5, power_draw_w=28.0)
    light = Payload(id="L", name="Light", weight_kg=0.1, power_draw_w=28.0)
    heavy_result = assess_mission(aircraft=_AIRCRAFT, payload=heavy, params=_PARAMS, weather=_CALM)
    light_result = assess_mission(aircraft=_AIRCRAFT, payload=light, params=_PARAMS, weather=_CALM)
    assert heavy_result.energy_required_wh > light_result.energy_required_wh
    assert heavy_result.effective_hover_power_w > light_result.effective_hover_power_w


def test_headwind_increases_cruise_energy() -> None:
    """A headwind lengthens the cruise leg and so costs energy."""
    windy = _CALM.model_copy(update={"wind_speed_mps": 10.0})
    calm_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM
    )
    windy_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=windy
    )
    assert windy_result.ground_speed_mps == 5.0
    assert windy_result.energy_breakdown.cruise_wh > calm_result.energy_breakdown.cruise_wh


def test_wind_at_or_above_cruise_speed_is_not_achievable() -> None:
    gale = _CALM.model_copy(update={"wind_speed_mps": 15.0})
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=gale)
    assert result.ground_speed_mps == 0.0
    assert result.safety_flags.cruise_achievable is False
    assert is_mission_viable(result) is False


def test_high_density_altitude_raises_required_power() -> None:
    """Hot and high thins the air, so holding a hover costs more."""
    sea_level = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM)
    high_params = _PARAMS.model_copy(update={"elevation_m": 2500.0})
    hot = _CALM.model_copy(update={"temperature_c": 35.0})
    high_hot = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=high_params, weather=hot
    )
    assert high_hot.air_density_ratio < sea_level.air_density_ratio
    assert high_hot.effective_hover_power_w > sea_level.effective_hover_power_w
    assert high_hot.energy_required_wh > sea_level.energy_required_wh


def test_cold_derates_usable_battery_capacity() -> None:
    """Cold is the dominant capacity killer and was previously ignored."""
    cold = _CALM.model_copy(update={"temperature_c": -10.0})
    warm_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_CALM
    )
    cold_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=cold
    )
    assert warm_result.battery_check.temperature_factor == 1.0
    assert cold_result.battery_check.temperature_factor == 0.65
    assert cold_result.battery_check.usable_capacity_wh < (
        warm_result.battery_check.usable_capacity_wh
    )


def test_assessment_flags_gusts_above_airframe_limit() -> None:
    """A gust beyond the limit is a NO-GO even when sustained wind is fine."""
    gusty = _CALM.model_copy(update={"wind_speed_mps": 5.0, "wind_gust_mps": 18.0})
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=gusty)
    assert result.safety_flags.wind_within_limits is True
    assert result.safety_flags.gust_within_limits is False
    assert is_mission_viable(result) is False


def test_temperature_check_is_two_sided() -> None:
    too_cold = _CALM.model_copy(update={"temperature_c": -30.0})
    too_hot = _CALM.model_copy(update={"temperature_c": 60.0})
    cold_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=too_cold
    )
    hot_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=too_hot
    )
    assert cold_result.safety_flags.temperature_within_limits is False
    assert hot_result.safety_flags.temperature_within_limits is False


def test_assessment_flags_high_wind() -> None:
    gusty = _CALM.model_copy(update={"wind_speed_mps": 13.0})
    result = assess_mission(aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=gusty)
    assert result.safety_flags.wind_within_limits is False
    assert is_mission_viable(result) is False


def test_assessment_flags_overweight_payload() -> None:
    heavy = Payload(id="H", name="Heavy", weight_kg=5.0, power_draw_w=10.0)
    result = assess_mission(aircraft=_AIRCRAFT, payload=heavy, params=_PARAMS, weather=_CALM)
    assert result.safety_flags.payload_within_limits is False
    assert result.payload_margin_kg < 0.0


def test_assessment_uses_target_altitude_for_density_altitude() -> None:
    """The target altitude is a live input, not a decorative form field."""
    at_surface = _PARAMS.model_copy(update={"target_altitude_m": 0.0})
    surface_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_NO_PAYLOAD, params=at_surface, weather=_CALM
    )
    aloft_result = assess_mission(
        aircraft=_AIRCRAFT, payload=_NO_PAYLOAD, params=_PARAMS, weather=_CALM
    )
    assert aloft_result.density_altitude_m - surface_result.density_altitude_m == 120.0


def test_zero_target_altitude_has_no_climb_or_descent_cost() -> None:
    ground_only = _PARAMS.model_copy(update={"target_altitude_m": 0.0})
    result = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=ground_only, weather=_CALM
    )
    assert result.energy_breakdown.climb_wh == 0.0
    assert result.energy_breakdown.descent_wh == 0.0
