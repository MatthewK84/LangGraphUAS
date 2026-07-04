def calculate_density_altitude(elevation_m: float, temp_c: float) -> float:
    isa_temp_c = 15.0 - (1.98 * (elevation_m / 1000.0))
    da_m = elevation_m + 118.8 * (temp_c - isa_temp_c)
    return round(da_m, 2)

def calculate_energy_required(
    distance_m: float, hover_time_s: float, cruise_speed_mps: float,
    hover_power_w: float, cruise_power_w: float, payload_power_w: float
) -> float:
    cruise_time_s = distance_m / cruise_speed_mps if cruise_speed_mps > 0 else 0
    hover_energy_j = (hover_power_w + payload_power_w) * hover_time_s
    cruise_energy_j = (cruise_power_w + payload_power_w) * cruise_time_s
    total_energy_wh = (hover_energy_j + cruise_energy_j) / 3600.0
    return round(total_energy_wh, 2)
