import json
import os
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from backend.models.state import MissionState
from backend.weather.live_api import get_live_weather
from backend.calculations.physics import calculate_density_altitude, calculate_energy_required
from backend.calculations.battery import check_battery_viability
from backend.database.core import SessionLocal
from backend.database.models import AircraftDB, PayloadDB

def row_to_dict(row):
    if not row: return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}

def validate_inputs(state: MissionState) -> MissionState:
    db = SessionLocal()
    try:
        ac_obj = db.query(AircraftDB).filter(AircraftDB.id == state.get("aircraft_id")).first()
        pl_obj = db.query(PayloadDB).filter(PayloadDB.id == state.get("payload_id")).first()
        
        if not ac_obj:
            state["report"] = "FATAL: Invalid aircraft selected."
            state["is_viable"] = False
            return state
            
        state["aircraft"] = row_to_dict(ac_obj)
        state["payload"] = row_to_dict(pl_obj) if pl_obj else row_to_dict(db.query(PayloadDB).filter(PayloadDB.id == "None").first())
    finally:
        db.close()
    return state

def fetch_weather_node(state: MissionState) -> MissionState:
    params = state.get("mission_params", {})
    state["weather"] = get_live_weather(params.get("latitude", 0.0), params.get("longitude", 0.0))
    return state

def calculate_performance(state: MissionState) -> MissionState:
    params = state["mission_params"]
    aircraft = state["aircraft"]
    payload = state["payload"]
    weather = state["weather"]

    da = calculate_density_altitude(params.get("elevation_m", 0.0), weather["temperature_c"])
    payload_margin_kg = aircraft["max_payload_kg"] - payload["weight_kg"]
    payload_safe = payload_margin_kg >= 0
    wind_safe = weather["wind_speed_mps"] <= aircraft["max_wind_mps"]
    temp_safe = weather["temperature_c"] <= aircraft["max_temp_c"]
    
    energy_req = calculate_energy_required(
        distance_m=params["distance_m"], hover_time_s=params["hover_time_s"],
        cruise_speed_mps=aircraft["cruise_speed_mps"], hover_power_w=aircraft["hover_power_w"],
        cruise_power_w=aircraft["cruise_power_w"], payload_power_w=payload["power_draw_w"]
    )
    
    battery_check = check_battery_viability(energy_req, aircraft["battery_wh"])
    is_viable = battery_check["is_viable"] and payload_safe and wind_safe and temp_safe
    
    state["calculations"] = {
        "density_altitude_m": da, "energy_required_wh": energy_req,
        "payload_margin_kg": round(payload_margin_kg, 2), "battery_check": battery_check,
        "safety_flags": {
            "battery_viable": battery_check["is_viable"], "payload_within_limits": payload_safe,
            "wind_within_limits": wind_safe, "temperature_within_limits": temp_safe
        }
    }
    state["is_viable"] = is_viable
    return state

def generate_report(state: MissionState) -> MissionState:
    if state.get("report"): return state
    calc_data = state.get("calculations", {})
    is_viable = state.get("is_viable", False)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        state["report"] = f"Mission Status: {'GO' if is_viable else 'NO-GO'}. Setup viable: {is_viable}."
        return state

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # Handle early validation failure
    if not calc_data:
        prompt = f"Mission Validation Failed. Setup viable: {is_viable}. Aircraft logic aborted."
    else:
        prompt = f"Analyze this structural/meteorological sUAS data. Clear: {'GO' if is_viable else 'NO-GO'}. Plane: {state['aircraft']['name']}. Cond: Temp: {state['weather']['temperature_c']}C, Wind: {state['weather']['wind_speed_mps']}m/s. Safety: {json.dumps(calc_data.get('safety_flags', {}))}. Calcs: {json.dumps(calc_data)}"
    
    response = llm.invoke([SystemMessage(content="You are an aviation safety officer."), HumanMessage(content=prompt)])
    state["report"] = response.content
    return state
