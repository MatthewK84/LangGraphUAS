"""Unit tests for the pure battery-budget calculation."""

from suas.calculations.battery import check_battery_viability


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
