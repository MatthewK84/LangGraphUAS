"""Unit tests for the pure battery-budget calculation."""

from suas.calculations.battery import (
    calculate_temperature_capacity_factor,
    check_battery_viability,
)


def test_battery_viable_with_ample_capacity() -> None:
    result = check_battery_viability(energy_required_wh=100.0, battery_capacity_wh=500.0)
    assert result.is_viable is True
    assert result.usable_capacity_wh == 400.0
    assert result.margin_wh == 300.0


def test_battery_not_viable_when_over_budget() -> None:
    result = check_battery_viability(energy_required_wh=450.0, battery_capacity_wh=500.0)
    assert result.is_viable is False
    assert result.margin_wh < 0.0


def test_battery_reserve_is_applied() -> None:
    result = check_battery_viability(
        energy_required_wh=0.0,
        battery_capacity_wh=100.0,
        reserve_percent=25.0,
    )
    assert result.usable_capacity_wh == 75.0


def test_capacity_factor_is_full_when_warm() -> None:
    assert calculate_temperature_capacity_factor(20.0) == 1.0
    assert calculate_temperature_capacity_factor(35.0) == 1.0


def test_capacity_factor_floors_when_very_cold() -> None:
    assert calculate_temperature_capacity_factor(-10.0) == 0.65
    assert calculate_temperature_capacity_factor(-40.0) == 0.65


def test_capacity_factor_interpolates_between_reference_points() -> None:
    """5 C is halfway between -10 C and 20 C, so halfway between 0.65 and 1.0."""
    assert abs(calculate_temperature_capacity_factor(5.0) - 0.825) < 0.001


def test_cold_reduces_usable_capacity() -> None:
    warm = check_battery_viability(100.0, 500.0, 20.0, 20.0)
    cold = check_battery_viability(100.0, 500.0, 20.0, -10.0)
    assert warm.usable_capacity_wh == 400.0
    assert cold.usable_capacity_wh == 260.0
    assert cold.margin_wh < warm.margin_wh


def test_cold_can_flip_a_viable_mission_to_not_viable() -> None:
    """The safety-relevant case: warm it fits, cold it does not."""
    warm = check_battery_viability(300.0, 500.0, 20.0, 20.0)
    cold = check_battery_viability(300.0, 500.0, 20.0, -10.0)
    assert warm.is_viable is True
    assert cold.is_viable is False
