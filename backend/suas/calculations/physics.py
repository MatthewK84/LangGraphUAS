"""Pure physics calculations.

Every function here is pure: identical inputs always yield identical outputs and
nothing external is read or mutated (Principle 7).

Modelling notes and their limits are documented per function. These are
engineering approximations for energy feasibility, not certified performance
data. See the data-provenance section of the README.
"""

from typing import Final

_METERS_PER_FOOT: Final[float] = 0.3048
_ISA_SEA_LEVEL_TEMP_C: Final[float] = 15.0
_GRAVITY_MPS2: Final[float] = 9.80665

# The textbook density-altitude constants are stated in feet: the ISA lapse rate
# is 1.98 C per 1000 ft and the temperature-deviation factor is 118.8 ft per C.
# This module works entirely in meters, so both are converted here rather than
# applied to metric inputs. Keeping the conversion explicit is deliberate: an
# earlier revision used the foot-valued constants directly against meters, which
# inflated the temperature term by a factor of ~3.28 (about 82.6 m per degree of
# deviation from 15 C) while the elevation term coincidentally still agreed.
_ISA_LAPSE_RATE_C_PER_M: Final[float] = 0.0065
_DENSITY_ALTITUDE_M_PER_C: Final[float] = 118.8 * _METERS_PER_FOOT

# ISA troposphere density relation: rho/rho0 = (1 - 2.25577e-5 * h)^4.25588.
_ISA_DENSITY_LAPSE_PER_M: Final[float] = 2.25577e-5
_ISA_DENSITY_EXPONENT: Final[float] = 4.25588

_SECONDS_PER_HOUR: Final[float] = 3600.0

# Momentum theory: induced hover power scales with thrust^1.5 / sqrt(density).
_MOMENTUM_MASS_EXPONENT: Final[float] = 1.5


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


def calculate_air_density_ratio(density_altitude_m: float) -> float:
    """Return air density as a fraction of ISA sea level for a density altitude.

    Density altitude is by definition the ISA altitude having this density, so
    the standard troposphere relation applies directly. Clamped at both ends:
    the relation is only valid below the tropopause, and density never goes
    non-positive.

    Args:
        density_altitude_m: Density altitude in meters.
    """
    base: float = 1.0 - (_ISA_DENSITY_LAPSE_PER_M * density_altitude_m)
    if base <= 0.0:
        return 0.01
    ratio: float = base**_ISA_DENSITY_EXPONENT
    return round(min(ratio, 1.5), 4)


def scale_power_for_conditions(
    base_power_w: float,
    mass_ratio: float,
    density_ratio: float,
) -> float:
    """Return a reference power figure corrected for mass and air density.

    From momentum theory, induced power varies as thrust^1.5 and inversely with
    the square root of air density. The published power figures are referenced
    to the airframe's own mass at ISA sea level, so the correction is applied as
    a ratio against that reference.

    This is applied to cruise power as well as hover power. Cruise is a mix of
    induced and parasite power and so does not follow this law exactly; the
    approximation is deliberately conservative in the high, hot and heavy
    regime that matters for a go/no-go.

    Args:
        base_power_w: Reference power draw in watts.
        mass_ratio: All-up mass divided by the airframe's reference mass.
        density_ratio: Air density as a fraction of ISA sea level.
    """
    if mass_ratio <= 0.0 or density_ratio <= 0.0:
        return base_power_w
    scaled: float = base_power_w * (mass_ratio**_MOMENTUM_MASS_EXPONENT) / (density_ratio**0.5)
    return round(scaled, 2)


def calculate_ground_speed(cruise_speed_mps: float, wind_speed_mps: float) -> float:
    """Return achievable ground speed against a worst-case headwind.

    The mission heading is not known, so no headwind component can be resolved.
    This assumes the entire cruise leg is flown directly into the reported wind,
    which is the worst case for the given distance and the right bias for a
    safety check. A non-positive result means the leg cannot be flown.

    Args:
        cruise_speed_mps: Airspeed in meters per second.
        wind_speed_mps: Sustained wind speed in meters per second.
    """
    return round(cruise_speed_mps - wind_speed_mps, 2)


def calculate_energy_required(
    *,
    distance_m: float,
    hover_time_s: float,
    ground_speed_mps: float,
    hover_power_w: float,
    cruise_power_w: float,
    payload_power_w: float,
) -> float:
    """Return hover plus cruise energy in watt-hours for the planned profile.

    Args:
        distance_m: Total cruise distance in meters.
        hover_time_s: Total hover time in seconds.
        ground_speed_mps: Achievable ground speed in meters per second.
        hover_power_w: Airframe power draw while hovering in watts.
        cruise_power_w: Airframe power draw while cruising in watts.
        payload_power_w: Payload power draw in watts.
    """
    cruise_time_s: float = distance_m / ground_speed_mps if ground_speed_mps > 0.0 else 0.0
    hover_energy_j: float = (hover_power_w + payload_power_w) * hover_time_s
    cruise_energy_j: float = (cruise_power_w + payload_power_w) * cruise_time_s
    total_energy_wh: float = (hover_energy_j + cruise_energy_j) / _SECONDS_PER_HOUR
    return round(total_energy_wh, 2)


def calculate_climb_energy(
    *,
    height_m: float,
    mass_kg: float,
    hover_power_w: float,
    payload_power_w: float,
    vertical_speed_mps: float,
    efficiency: float,
) -> float:
    """Return energy in watt-hours to climb to the operating altitude.

    Modelled as the power needed to stay airborne for the duration of the climb,
    plus the potential energy gained divided by a propulsive efficiency.

    Args:
        height_m: Height to climb above the launch point in meters.
        mass_kg: All-up mass in kilograms.
        hover_power_w: Condition-corrected hover power in watts.
        payload_power_w: Payload power draw in watts.
        vertical_speed_mps: Climb rate in meters per second.
        efficiency: Propulsive efficiency for the potential-energy term.
    """
    if height_m <= 0.0 or vertical_speed_mps <= 0.0 or efficiency <= 0.0:
        return 0.0
    climb_time_s: float = height_m / vertical_speed_mps
    hold_energy_j: float = (hover_power_w + payload_power_w) * climb_time_s
    potential_energy_j: float = (mass_kg * _GRAVITY_MPS2 * height_m) / efficiency
    return round((hold_energy_j + potential_energy_j) / _SECONDS_PER_HOUR, 2)


def calculate_descent_energy(
    *,
    height_m: float,
    hover_power_w: float,
    payload_power_w: float,
    vertical_speed_mps: float,
) -> float:
    """Return energy in watt-hours to descend from the operating altitude.

    A powered descent still has to hold the aircraft up, so this charges hover
    power for the descent duration and takes no credit for recovered potential
    energy.

    Args:
        height_m: Height to descend in meters.
        hover_power_w: Condition-corrected hover power in watts.
        payload_power_w: Payload power draw in watts.
        vertical_speed_mps: Descent rate in meters per second.
    """
    if height_m <= 0.0 or vertical_speed_mps <= 0.0:
        return 0.0
    descent_time_s: float = height_m / vertical_speed_mps
    return round(((hover_power_w + payload_power_w) * descent_time_s) / _SECONDS_PER_HOUR, 2)
