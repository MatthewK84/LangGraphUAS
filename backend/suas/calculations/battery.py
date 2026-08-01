"""Pure battery-budget calculation."""

from typing import Final

from suas.schemas.responses import BatteryCheck

DEFAULT_RESERVE_PERCENT: Final[float] = 20.0

# Lithium-polymer packs deliver less usable energy as they get cold: internal
# resistance rises and the pack hits its voltage floor sooner. Modelled as a
# piecewise-linear derate between two reference points, flat above the warm
# point. These are representative figures for the chemistry, not a measured
# curve for any specific pack, and they are deliberately not aggressive.
_WARM_TEMP_C: Final[float] = 20.0
_COLD_TEMP_C: Final[float] = -10.0
_COLD_CAPACITY_FACTOR: Final[float] = 0.65


def calculate_temperature_capacity_factor(temperature_c: float) -> float:
    """Return the fraction of nameplate capacity usable at a temperature.

    Cold is the dominant capacity killer for these packs, and the previous
    revision ignored temperature entirely, which biased every cold-weather
    energy budget optimistic.

    Args:
        temperature_c: Ambient air temperature in degrees Celsius.
    """
    if temperature_c >= _WARM_TEMP_C:
        return 1.0
    if temperature_c <= _COLD_TEMP_C:
        return _COLD_CAPACITY_FACTOR
    span: float = _WARM_TEMP_C - _COLD_TEMP_C
    fraction: float = (temperature_c - _COLD_TEMP_C) / span
    factor: float = _COLD_CAPACITY_FACTOR + fraction * (1.0 - _COLD_CAPACITY_FACTOR)
    return round(factor, 4)


def check_battery_viability(
    energy_required_wh: float,
    battery_capacity_wh: float,
    reserve_percent: float = DEFAULT_RESERVE_PERCENT,
    temperature_c: float = _WARM_TEMP_C,
) -> BatteryCheck:
    """Return the battery energy budget for a mission.

    Args:
        energy_required_wh: Energy the mission profile demands, in watt-hours.
        battery_capacity_wh: Nameplate battery capacity, in watt-hours.
        reserve_percent: Reserve to withhold from usable capacity, as a percent.
        temperature_c: Ambient temperature, used to derate cold capacity.
    """
    temperature_factor: float = calculate_temperature_capacity_factor(temperature_c)
    available_wh: float = battery_capacity_wh * temperature_factor
    usable_capacity_wh: float = available_wh * (1.0 - (reserve_percent / 100.0))
    margin_wh: float = usable_capacity_wh - energy_required_wh
    return BatteryCheck(
        energy_required_wh=round(energy_required_wh, 2),
        usable_capacity_wh=round(usable_capacity_wh, 2),
        margin_wh=round(margin_wh, 2),
        reserve_percent=reserve_percent,
        temperature_factor=temperature_factor,
        is_viable=margin_wh >= 0.0,
    )
