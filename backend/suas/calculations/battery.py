"""Pure battery-budget calculation."""

from typing import Final

from suas.schemas.responses import BatteryCheck

_DEFAULT_RESERVE_PERCENT: Final[float] = 20.0


def check_battery_viability(
    energy_required_wh: float,
    battery_capacity_wh: float,
    reserve_percent: float = _DEFAULT_RESERVE_PERCENT,
) -> BatteryCheck:
    """Return the battery energy budget for a mission.

    Args:
        energy_required_wh: Energy the mission profile demands, in watt-hours.
        battery_capacity_wh: Nameplate battery capacity, in watt-hours.
        reserve_percent: Reserve to withhold from usable capacity, as a percent.
    """
    usable_capacity_wh: float = battery_capacity_wh * (1.0 - (reserve_percent / 100.0))
    margin_wh: float = usable_capacity_wh - energy_required_wh
    return BatteryCheck(
        energy_required_wh=round(energy_required_wh, 2),
        usable_capacity_wh=round(usable_capacity_wh, 2),
        margin_wh=round(margin_wh, 2),
        reserve_percent=reserve_percent,
        is_viable=margin_wh >= 0.0,
    )
