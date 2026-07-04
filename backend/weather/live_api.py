import requests
import logging

logger = logging.getLogger("uvicorn.error")

def get_live_weather(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": ["temperature_2m", "wind_speed_10m", "wind_direction_10m", "relative_humidity_2m"],
        "wind_speed_unit": "ms", "timezone": "auto"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        current = response.json().get("current", {})
        return {
            "temperature_c": current.get("temperature_2m", 15.0),
            "wind_speed_mps": current.get("wind_speed_10m", 0.0),
            "wind_direction": current.get("wind_direction_10m", 0),
            "humidity_percent": current.get("relative_humidity_2m", 50.0),
            "conditions": "Live Meteorological Feed"
        }
    except Exception as e:
        logger.error(f"Weather API failed: {str(e)}")
        return {
            "temperature_c": 15.0, "wind_speed_mps": 0.0, "wind_direction": 0,
            "humidity_percent": 50.0, "conditions": "Fallback Defaults"
        }
