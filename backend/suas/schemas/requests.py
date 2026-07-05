"""Inbound request models.

Every field is validated at the API boundary so that downstream code never
performs unchecked dictionary access (Principle 8/9).
"""

from pydantic import BaseModel, Field


class MissionParams(BaseModel):
    """Mission geometry and environment inputs."""

    distance_m: float = Field(ge=0.0)
    hover_time_s: float = Field(ge=0.0)
    target_altitude_m: float = Field(ge=0.0)
    elevation_m: float
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class MissionRequest(BaseModel):
    """A request to plan and assess a single mission."""

    aircraft_id: str = Field(min_length=1)
    payload_id: str = Field(min_length=1)
    mission_params: MissionParams
    thread_id: str | None = Field(default=None)
