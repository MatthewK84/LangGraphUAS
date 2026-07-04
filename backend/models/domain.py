from pydantic import BaseModel
from typing import Optional

class Aircraft(BaseModel):
    id: str
    name: str
    weight_kg: float
    max_payload_kg: float
    battery_wh: float
    max_wind_mps: float
    cruise_speed_mps: float
    hover_power_w: float
    cruise_power_w: float
    max_temp_c: float

class Payload(BaseModel):
    id: str
    name: str
    weight_kg: float
    power_draw_w: float

class MissionParams(BaseModel):
    distance_m: float
    hover_time_s: float
    target_altitude_m: float
    elevation_m: float
    latitude: float
    longitude: float
