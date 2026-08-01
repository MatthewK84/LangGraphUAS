"""Pure physics calculations.

Every function here is pure: identical inputs always yield identical outputs and
nothing external is read or mutated (Principle 7).
"""

from typing import Final

_METERS_PER_FOOT: Final[float] = 0.3048
_ISA_SEA_LEVEL_TEMP_C: Final[float] = 15.0

# The textbook density-altitude constants are stated in feet: the ISA lapse rate
# is 1.98 C per 1000 ft and the temperature-deviation factor is 118.8 ft per C.
# This module works entirely in meters, so both are converted here rather than
# applied to metric inputs. Keeping the conversion explicit is deliberate: an
# earlier revision used the foot-valued constants directly against meters, which
# inflated the temperature term by a factor of ~3.28 (about 82.6 m per degree of
# deviation from 15 C) while the elevation term coincidentally still agreed.
_ISA_LAPSE_RATE_C_PER_M: Final[float] = 0.0065
_DENSITY_ALTITUDE_M_PER_C: Final[float] = 118.8 * _METERS_PER_FOOT

_SECONDS_PER_HOUR: Final[float] = 3600.0


def calculate_density_altitude(elevation_m: float, temp_c: float, agl_m: float = 0.0) -> float:
    """Return density altitude in meters at the mission's operating altitude.

    The surface temperature is extrapolated up to the operating altitude with
    the ISA lapse rate before the deviation from standard is applied.

    Args:
        elevation_m: Launch-point elevation above sea level in meters.
        temp_c: Ambient air temperature at ``elevation_m`` in degrees Celsius.
        agl_m: Operating height above the launch point in meters.
    """
    operating_altitude_m: float = elevation_m + agl_m
    oat_at_altitude_c: float = temp_c - (_ISA_LAPSE_RATE_C_PER_M * agl_m)
    isa_temp_c: float = _ISA_SEA_LEVEL_TEMP_C - (_ISA_LAPSE_RATE_C_PER_M * operating_altitude_m)
    density_altitude_m: float = operating_altitude_m + _DENSITY_ALTITUDE_M_PER_C * (
        oat_at_altitude_c - isa_temp_c
    )
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
