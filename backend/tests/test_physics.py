"""Unit tests for the pure physics calculations."""

from suas.calculations.physics import calculate_density_altitude, calculate_energy_required


def test_density_altitude_at_isa_sea_level_is_zero() -> None:
    assert calculate_density_altitude(0.0, 15.0) == 0.0


def test_density_altitude_rises_with_temperature() -> None:
    hot = calculate_density_altitude(0.0, 30.0)
    assert hot > 0.0


def test_density_altitude_below_isa_is_negative() -> None:
    cold = calculate_density_altitude(0.0, 0.0)
    assert cold < 0.0


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
