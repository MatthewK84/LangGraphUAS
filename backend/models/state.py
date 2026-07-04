from typing import TypedDict, Dict, Any

class MissionState(TypedDict, total=False):
    mission_params: Dict[str, Any]
    aircraft_id: str
    payload_id: str
    weather: Dict[str, Any]
    aircraft: Dict[str, Any]
    payload: Dict[str, Any]
    calculations: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    is_viable: bool
    report: str
