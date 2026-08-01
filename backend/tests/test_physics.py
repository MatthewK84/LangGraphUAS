"""Unit tests for the pure physics calculations.

These assert magnitudes, not just signs. An earlier revision of
``calculate_density_altitude`` applied foot-valued constants to metric inputs
and was wrong by ~82.6 m per degree of deviation from 15 C; every sign-and-
monotonicity assertion still passed. The oracle below is derived independently
in feet from the textbook constants and then converted, so it does not restate
the implementation.
"""

from suas.calculations.physics import calculate_density_altitude, calculate_energy_required

_METERS_PER_FOOT = 0.3048


def _reference_density_altitude_m(elevation_m: float, temp_c: float) -> float:
    """Return density altitude computed in feet from textbook constants.

    Independent of the implementation: works in feet with the published
    1.98 C/1000 ft lapse rate and 118.8 ft/C deviation factor, then converts.
    """
    pressure_altitude_ft = elevation_m / _METERS_PER_FOOT
    isa_temp_c = 15.0 - 1.98 * (pressure_altitude_ft / 1000.0)
    density_altitude_ft = pressure_altitude_ft + 118.8 * (temp_c - isa_temp_c)
    return density_altitude_ft * _METERS_PER_FOOT


def test_density_altitude_at_isa_sea_level_is_zero() -> None:
    assert calculate_density_altitude(0.0, 15.0) == 0.0


def test_density_altitude_sea_level_hot_day_matches_published_value() -> None:
    """35 C at sea level is the classic ~2,380 ft (~725 m) density altitude."""
    result = calculate_density_altitude(0.0, 35.0)
    assert result == 724.2
    assert abs(result / _METERS_PER_FOOT - 2376.0) < 1.0


def test_density_altitude_at_elevation_matches_independent_oracle() -> None:
    for elevation_m, temp_c in [(0.0, 35.0), (1600.0, 30.0), (0.0, -5.0), (2500.0, 5.0)]:
        result = calculate_density_altitude(elevation_m, temp_c)
        expected = _reference_density_altitude_m(elevation_m, temp_c)
        assert abs(result - expected) < 1.0, f"{elevation_m} m / {temp_c} C"


def test_density_altitude_temperature_sensitivity_is_metric() -> None:
    """Each degree above ISA adds ~36.2 m, not the foot-valued 118.8."""
    delta = calculate_density_altitude(0.0, 16.0) - calculate_density_altitude(0.0, 15.0)
    assert abs(delta - 36.21) < 0.05


def test_density_altitude_below_isa_is_negative() -> None:
    assert calculate_density_altitude(0.0, 0.0) < 0.0
    assert calculate_density_altitude(0.0, -5.0) == -724.2


def test_density_altitude_adds_operating_height() -> None:
    """Under a standard lapse rate, climbing h meters raises DA by exactly h."""
    at_surface = calculate_density_altitude(1600.0, 30.0)
    aloft = calculate_density_altitude(1600.0, 30.0, 120.0)
    assert aloft - at_surface == 120.0


def test_density_altitude_defaults_to_surface_when_no_agl_given() -> None:
    assert calculate_density_altitude(1600.0, 30.0) == calculate_density_altitude(
        1600.0, 30.0, 0.0
    )


def test_energy_required_hover_only() -> None:
    energy = calculate_energy_required(
        distance_m=0.0,
        hover_time_s=3600.0,
        cruise_speed_mps=15.0,
        hover_power_w=800.0,
        cruise_power_w=690.0,
        payload_power_w=0.0,
    )
    assert energy == 800.0


def test_energy_required_combines_hover_and_cruise() -> None:
    """5000 m at 15 m/s is 333.33 s cruise; hover 600 s. Payload draws in both."""
    energy = calculate_energy_required(
        distance_m=5000.0,
        hover_time_s=600.0,
        cruise_speed_mps=15.0,
        hover_power_w=800.0,
        cruise_power_w=690.0,
        payload_power_w=10.0,
    )
    # (810 W * 600 s + 700 W * 333.333 s) / 3600 = 199.81 Wh
    assert energy == 199.81


def test_energy_required_scales_linearly_with_hover_time() -> None:
    def hover(seconds: float) -> float:
        return calculate_energy_required(
            distance_m=0.0,
            hover_time_s=seconds,
            cruise_speed_mps=15.0,
            hover_power_w=900.0,
            cruise_power_w=690.0,
            payload_power_w=0.0,
        )

    assert hover(1800.0) == 450.0
    assert hover(3600.0) == 900.0


def test_energy_required_zero_speed_ignores_cruise() -> None:
    energy = calculate_energy_required(
        distance_m=5000.0,
        hover_time_s=0.0,
        cruise_speed_mps=0.0,
        hover_power_w=800.0,
        cruise_power_w=690.0,
        payload_power_w=10.0,
    )
    assert energy == 0.0
