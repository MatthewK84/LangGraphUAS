"""Graph state definition.

The state holds only JSON-native structures (dicts, str, float, bool). Pydantic
models are converted with ``model_dump`` before being written to state so that
checkpoint serialization stays simple and safe under strict msgpack settings.
"""

from typing import Any, TypedDict


class MissionState(TypedDict, total=False):
    """Shared state threaded through the mission planning graph."""

    aircraft_id: str
    payload_id: str
    mission_params: dict[str, Any]
    aircraft: dict[str, Any] | None
    payload: dict[str, Any] | None
    weather: dict[str, Any] | None
    calculations: dict[str, Any] | None
    is_viable: bool
    report: str
    error: str | None
