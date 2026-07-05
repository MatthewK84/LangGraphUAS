"""Pure mission assessment.

Combines the individual physics and battery calculations into a single
deterministic result. Kept pure so it is trivial to unit test (Principle 7).
"""

from suas.calculations.battery import check_battery_viability
from suas.calculations.physics import calculate_density_altitude, calculate_energy_required
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import Calculations, SafetyFlags, WeatherReading


def _build_safety_flags(
    *,
    battery_viable: bool,
    payload_margin_kg: float,
    wind_speed_mps: float,
    temperature_c: float,
    aircraft: Aircraft,
) -> SafetyFlags:
    """Return the four independent safety constraint flags."""
    return SafetyFlags(
        battery_viable=battery_viable,
        payload_within_limits=payload_margin_kg >= 0.0,
        wind_within_limits=wind_speed_mps <= aircraft.max_wind_mps,
        temperature_within_limits=temperature_c <= aircraft.max_temp_c,
    )


def assess_mission(
    *,
    aircraft: Aircraft,
    payload: Payload,
    params: MissionParams,
    weather: WeatherReading,
) -> Calculations:
    """Return the full deterministic assessment for a planned mission."""
    density_altitude_m: float = calculate_density_altitude(params.elevation_m, weather.temperature_c)
    payload_margin_kg: float = round(aircraft.max_payload_kg - payload.weight_kg, 2)
    energy_required_wh: float = calculate_energy_required(
        distance_m=params.distance_m,
        hover_time_s=params.hover_time_s,
        cruise_speed_mps=aircraft.cruise_speed_mps,
        hover_power_w=aircraft.hover_power_w,
        cruise_power_w=aircraft.cruise_power_w,
        payload_power_w=payload.power_draw_w,
    )
    battery_check = check_battery_viability(energy_required_wh, aircraft.battery_wh)
    safety_flags = _build_safety_flags(
        battery_viable=battery_check.is_viable,
        payload_margin_kg=payload_margin_kg,
        wind_speed_mps=weather.wind_speed_mps,
        temperature_c=weather.temperature_c,
        aircraft=aircraft,
    )
    return Calculations(
        density_altitude_m=density_altitude_m,
        energy_required_wh=energy_required_wh,
        payload_margin_kg=payload_margin_kg,
        battery_check=battery_check,
        safety_flags=safety_flags,
    )


def is_mission_viable(calculations: Calculations) -> bool:
    """Return whether every safety constraint passed."""
    flags = calculations.safety_flags
    return (
        flags.battery_viable
        and flags.payload_within_limits
        and flags.wind_within_limits
        and flags.temperature_within_limits
    )
