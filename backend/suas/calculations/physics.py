"""Pure physics calculations.

Every function here is pure: identical inputs always yield identical outputs and
nothing external is read or mutated (Principle 7).
"""

from typing import Final

_ISA_SEA_LEVEL_TEMP_C: Final[float] = 15.0
_ISA_LAPSE_RATE_C_PER_KM: Final[float] = 1.98
_DENSITY_ALTITUDE_FACTOR: Final[float] = 118.8
_SECONDS_PER_HOUR: Final[float] = 3600.0


def calculate_density_altitude(elevation_m: float, temp_c: float) -> float:
    """Return density altitude in meters for a given elevation and temperature.

    Args:
        elevation_m: Field elevation above sea level in meters.
        temp_c: Ambient air temperature in degrees Celsius.
    """
    isa_temp_c: float = _ISA_SEA_LEVEL_TEMP_C - (_ISA_LAPSE_RATE_C_PER_KM * (elevation_m / 1000.0))
    density_altitude_m: float = elevation_m + _DENSITY_ALTITUDE_FACTOR * (temp_c - isa_temp_c)
    return round(density_altitude_m, 2)


def calculate_energy_required(
    *,
    distance_m: float,
    hover_time_s: float,
    cruise_speed_mps: float,
    hover_power_w: float,
    cruise_power_w: float,
    payload_power_w: float,
) -> float:
    """Return total energy required in watt-hours for the planned profile.

    Args:
        distance_m: Total cruise distance in meters.
        hover_time_s: Total hover time in seconds.
        cruise_speed_mps: Cruise ground speed in meters per second.
        hover_power_w: Airframe power draw while hovering in watts.
        cruise_power_w: Airframe power draw while cruising in watts.
        payload_power_w: Payload power draw in watts.
    """
    cruise_time_s: float = distance_m / cruise_speed_mps if cruise_speed_mps > 0.0 else 0.0
    hover_energy_j: float = (hover_power_w + payload_power_w) * hover_time_s
    cruise_energy_j: float = (cruise_power_w + payload_power_w) * cruise_time_s
    total_energy_wh: float = (hover_energy_j + cruise_energy_j) / _SECONDS_PER_HOUR
    return round(total_energy_wh, 2)
