def check_battery_viability(energy_required_wh: float, battery_capacity_wh: float, reserve_percent: float = 20.0) -> dict:
    usable_capacity_wh = battery_capacity_wh * (1.0 - (reserve_percent / 100.0))
    margin_wh = usable_capacity_wh - energy_required_wh
    is_viable = margin_wh >= 0
    return {
        "energy_required_wh": round(energy_required_wh, 2),
        "usable_capacity_wh": round(usable_capacity_wh, 2),
        "margin_wh": round(margin_wh, 2),
        "reserve_percent": reserve_percent,
        "is_viable": is_viable
    }
