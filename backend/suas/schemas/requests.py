"""Inbound request models.

Every field is validated at the API boundary so that downstream code never
performs unchecked dictionary access (Principle 8/9).
"""

from typing import Literal

from pydantic import BaseModel, Field

from suas.schemas.assessment import AssessmentMode


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
    # What the caller would like this plan to count as. The backend decides what
    # it actually counts as; see suas.calculations.gate.
    assessment_mode: AssessmentMode = AssessmentMode.ADVISORY


class MissionEdits(BaseModel):
    """The fields an operator may revise at the review step.

    Deliberately narrow. Anything not offered here cannot be changed between the
    assessment and the signature, so a client cannot quietly rewrite the mission
    while the operator is looking at numbers for a different one.
    """

    target_altitude_m: float | None = Field(default=None, ge=0.0)
    hover_time_s: float | None = Field(default=None, ge=0.0)
    payload_id: str | None = Field(default=None, min_length=1)


class AckRequest(BaseModel):
    """An operator's decision on a pending assessment."""

    action: Literal["confirm", "edit", "abort"]
    actor: str = Field(min_length=1, max_length=200)
    # The assessment the operator was actually shown. When present it is checked
    # against the current one, so a signature cannot be applied to numbers that
    # changed underneath it.
    inputs_hash: str | None = Field(default=None, min_length=1, max_length=128)
    edits: MissionEdits | None = Field(default=None)
