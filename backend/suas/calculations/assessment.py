"""Pure mission assessment.

Combines the individual physics and battery calculations into a single
deterministic result. Kept pure so it is trivial to unit test (Principle 7).

The model corrects power for all-up mass and air density, charges energy for
climb and descent, penalises cruise for a worst-case headwind, derates battery
capacity when cold, and checks gusts and cold limits as well as steady wind and
heat. An earlier revision did none of these, and every one of those omissions
biased the result toward GO.
"""

from suas.calculations.battery import DEFAULT_RESERVE_PERCENT, check_battery_viability
from suas.calculations.physics import (
    calculate_air_density_ratio,
    calculate_climb_energy,
    calculate_density_altitude,
    calculate_descent_energy,
    calculate_energy_required,
    calculate_ground_speed,
    scale_power_for_conditions,
)
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import (
    Calculations,
    EnergyBreakdown,
    SafetyFlags,
    WeatherReading,
)

DEFAULT_VERTICAL_SPEED_MPS: float = 3.0
DEFAULT_CLIMB_EFFICIENCY: float = 0.6


def _build_safety_flags(
    *,
    battery_viable: bool,
    payload_margin_kg: float,
    ground_speed_mps: float,
    weather: WeatherReading,
    aircraft: Aircraft,
) -> SafetyFlags:
    """Return the independent safety constraint flags.

    The temperature check is two-sided: cold limits airframe and pack behaviour
    just as heat does. Gusts are checked against the same airframe wind limit as
    sustained wind, since it is the gust that actually exceeds control authority.
    """
    return SafetyFlags(
        battery_viable=battery_viable,
        payload_within_limits=payload_margin_kg >= 0.0,
        wind_within_limits=weather.wind_speed_mps <= aircraft.max_wind_mps,
        gust_within_limits=weather.wind_gust_mps <= aircraft.max_wind_mps,
        temperature_within_limits=(
            aircraft.min_temp_c <= weather.temperature_c <= aircraft.max_temp_c
        ),
        cruise_achievable=ground_speed_mps > 0.0,
    )


def _build_energy_breakdown(
    *,
    payload: Payload,
    params: MissionParams,
    hover_power_w: float,
    cruise_power_w: float,
    ground_speed_mps: float,
    all_up_mass_kg: float,
    vertical_speed_mps: float,
    climb_efficiency: float,
) -> EnergyBreakdown:
    """Return the per-phase energy demand for the planned profile."""
    climb_wh: float = calculate_climb_energy(
        height_m=params.target_altitude_m,
        mass_kg=all_up_mass_kg,
        hover_power_w=hover_power_w,
        payload_power_w=payload.power_draw_w,
        vertical_speed_mps=vertical_speed_mps,
        efficiency=climb_efficiency,
    )
    descent_wh: float = calculate_descent_energy(
        height_m=params.target_altitude_m,
        hover_power_w=hover_power_w,
        payload_power_w=payload.power_draw_w,
        vertical_speed_mps=vertical_speed_mps,
    )
    hover_wh: float = calculate_energy_required(
        distance_m=0.0,
        hover_time_s=params.hover_time_s,
        ground_speed_mps=ground_speed_mps,
        hover_power_w=hover_power_w,
        cruise_power_w=cruise_power_w,
        payload_power_w=payload.power_draw_w,
    )
    cruise_wh: float = calculate_energy_required(
        distance_m=params.distance_m,
        hover_time_s=0.0,
        ground_speed_mps=ground_speed_mps,
        hover_power_w=hover_power_w,
        cruise_power_w=cruise_power_w,
        payload_power_w=payload.power_draw_w,
    )
    total: float = round(climb_wh + cruise_wh + hover_wh + descent_wh, 2)
    return EnergyBreakdown(
        climb_wh=climb_wh,
        cruise_wh=cruise_wh,
        hover_wh=hover_wh,
        descent_wh=descent_wh,
        total_wh=total,
    )


def assess_mission(
    *,
    aircraft: Aircraft,
    payload: Payload,
    params: MissionParams,
    weather: WeatherReading,
    reserve_percent: float = DEFAULT_RESERVE_PERCENT,
    vertical_speed_mps: float = DEFAULT_VERTICAL_SPEED_MPS,
    climb_efficiency: float = DEFAULT_CLIMB_EFFICIENCY,
) -> Calculations:
    """Return the full deterministic assessment for a planned mission.

    Args:
        aircraft: The airframe being flown.
        payload: The mounted payload.
        params: Mission geometry and environment inputs.
        weather: Current conditions at the launch point.
        reserve_percent: Battery reserve withheld from usable capacity.
        vertical_speed_mps: Assumed climb and descent rate.
        climb_efficiency: Propulsive efficiency for the climb energy term.
    """
    density_altitude_m: float = calculate_density_altitude(
        params.elevation_m,
        weather.temperature_c,
        params.target_altitude_m,
    )
    density_ratio: float = calculate_air_density_ratio(density_altitude_m)
    all_up_mass_kg: float = round(aircraft.weight_kg + payload.weight_kg, 3)
    mass_ratio: float = all_up_mass_kg / aircraft.weight_kg
    hover_power_w: float = scale_power_for_conditions(
        aircraft.hover_power_w, mass_ratio, density_ratio
    )
    cruise_power_w: float = scale_power_for_conditions(
        aircraft.cruise_power_w, mass_ratio, density_ratio
    )
    ground_speed_mps: float = calculate_ground_speed(
        aircraft.cruise_speed_mps, weather.wind_speed_mps
    )
    payload_margin_kg: float = round(aircraft.max_payload_kg - payload.weight_kg, 2)
    breakdown: EnergyBreakdown = _build_energy_breakdown(
        payload=payload,
        params=params,
        hover_power_w=hover_power_w,
        cruise_power_w=cruise_power_w,
        ground_speed_mps=ground_speed_mps,
        all_up_mass_kg=all_up_mass_kg,
        vertical_speed_mps=vertical_speed_mps,
        climb_efficiency=climb_efficiency,
    )
    battery_check = check_battery_viability(
        breakdown.total_wh,
        aircraft.battery_wh,
        reserve_percent,
        weather.temperature_c,
    )
    safety_flags = _build_safety_flags(
        battery_viable=battery_check.is_viable,
        payload_margin_kg=payload_margin_kg,
        ground_speed_mps=ground_speed_mps,
        weather=weather,
        aircraft=aircraft,
    )
    return Calculations(
        density_altitude_m=density_altitude_m,
        air_density_ratio=density_ratio,
        energy_required_wh=breakdown.total_wh,
        energy_breakdown=breakdown,
        payload_margin_kg=payload_margin_kg,
        all_up_mass_kg=all_up_mass_kg,
        ground_speed_mps=ground_speed_mps,
        effective_hover_power_w=hover_power_w,
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
        and flags.gust_within_limits
        and flags.temperature_within_limits
        and flags.cruise_achievable
    )
