"""Graph nodes.

Each node is produced by a factory that closes over its dependencies, so nodes
carry no global state and are individually testable. Nodes return only the state
keys they update, which LangGraph merges into the running state.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Final

from suas.calculations.assessment import (
    assess_mission,
    build_assessment,
    insufficient_data_assessment,
    is_mission_viable,
)
from suas.db.repository import get_aircraft, get_payload
from suas.errors import ReportGenerationError
from suas.graph.dependencies import GraphDependencies
from suas.graph.seal import find_contradiction
from suas.graph.state import MissionState
from suas.schemas.assessment import AssessmentMode, Decision, DeterministicAssessment
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import Calculations, WeatherReading

logger: Final[logging.Logger] = logging.getLogger(__name__)

NodeFn = Callable[[MissionState], Awaitable[MissionState]]

_NO_PAYLOAD_ID: Final[str] = "None"
_INVALID_AIRCRAFT_REPORT: Final[str] = "FATAL: Invalid aircraft selected."


def make_validate_node(deps: GraphDependencies) -> NodeFn:
    """Return a node that resolves aircraft and payload from the database."""

    async def validate_inputs(state: MissionState) -> MissionState:
        async with deps.session_factory() as session:
            aircraft: Aircraft | None = await get_aircraft(session, state["aircraft_id"])
            if aircraft is None:
                logger.warning("Rejected unknown aircraft id: %s", state["aircraft_id"])
                assessment = insufficient_data_assessment(
                    reason=f"Unknown aircraft id: {state['aircraft_id']}.",
                    inputs={
                        "aircraft_id": state["aircraft_id"],
                        "payload_id": state.get("payload_id"),
                        "mission_params": state.get("mission_params"),
                    },
                )
                return {
                    "assessment": assessment.model_dump(mode="json"),
                    "is_viable": False,
                    "error": "invalid_aircraft",
                    "report": _INVALID_AIRCRAFT_REPORT,
                }
            payload: Payload | None = await get_payload(session, state["payload_id"])
            if payload is None:
                payload = await get_payload(session, _NO_PAYLOAD_ID)
        payload_dump: dict[str, Any] | None = payload.model_dump() if payload else None
        return {"aircraft": aircraft.model_dump(), "payload": payload_dump, "is_viable": True}

    return validate_inputs


def make_weather_node(deps: GraphDependencies) -> NodeFn:
    """Return a node that fetches live weather for the mission coordinate."""

    async def fetch_weather(state: MissionState) -> MissionState:
        params = MissionParams.model_validate(state["mission_params"])
        reading: WeatherReading = await deps.weather.fetch(params.latitude, params.longitude)
        return {"weather": reading.model_dump()}

    return fetch_weather


def make_calculations_node(deps: GraphDependencies) -> NodeFn:
    """Return a node that runs the deterministic mission assessment."""

    async def calculate(state: MissionState) -> MissionState:
        aircraft = Aircraft.model_validate(state["aircraft"])
        payload = Payload.model_validate(state["payload"])
        params = MissionParams.model_validate(state["mission_params"])
        weather = WeatherReading.model_validate(state["weather"])
        calculations: Calculations = assess_mission(
            aircraft=aircraft,
            payload=payload,
            params=params,
            weather=weather,
            reserve_percent=deps.battery_reserve_percent,
            vertical_speed_mps=deps.vertical_speed_mps,
            climb_efficiency=deps.climb_efficiency,
        )
        requested_mode = AssessmentMode(
            str(state.get("requested_mode", AssessmentMode.ADVISORY.value))
        )
        assessment: DeterministicAssessment = build_assessment(
            calculations=calculations,
            requested_mode=requested_mode,
            weather=weather,
            inputs={
                "aircraft": aircraft.model_dump(mode="json"),
                "payload": payload.model_dump(mode="json"),
                "mission_params": params.model_dump(mode="json"),
                "weather": weather.model_dump(mode="json"),
                "requested_mode": requested_mode.value,
            },
        )
        return {
            "calculations": calculations.model_dump(),
            "assessment": assessment.model_dump(mode="json"),
            "is_viable": is_mission_viable(calculations),
        }

    return calculate


def make_report_node(deps: GraphDependencies) -> NodeFn:
    """Return a node that produces the natural-language safety brief."""

    async def generate_report(state: MissionState) -> MissionState:
        if state.get("report"):
            return {}
        is_viable: bool = bool(state.get("is_viable", False))
        calc_dump = state.get("calculations")
        aircraft_dump = state.get("aircraft")
        if calc_dump is None or aircraft_dump is None:
            return {"report": f"Mission validation failed. Viable: {is_viable}."}
        try:
            report: str = await deps.report.generate(
                is_viable=is_viable,
                aircraft_name=str(aircraft_dump.get("name", "unknown")),
                weather=WeatherReading.model_validate(state["weather"]),
                calculations=Calculations.model_validate(calc_dump),
            )
        except ReportGenerationError:
            logger.warning("Falling back to deterministic report text")
            report = f"Mission status: {'GO' if is_viable else 'NO-GO'}. Narrative unavailable."
        return {"report": report, "seal_violations": _check_prose(report, state)}

    return generate_report


def _check_prose(report: str, state: MissionState) -> list[str]:
    """Return seal violations found in generated prose.

    The decision comes from the sealed assessment, not from this text, so a
    contradiction here cannot change what the operator is told to do -- the
    dashboard renders the verdict from the assessment on a separate path. It
    still means something upstream produced a brief at odds with the math, so it
    is named and counted rather than passed along quietly.
    """
    assessment_dump = state.get("assessment")
    if assessment_dump is None:
        return []
    decision = Decision(str(assessment_dump.get("decision", Decision.INSUFFICIENT_DATA.value)))
    found: str | None = find_contradiction(report, decision)
    if found is None:
        return []
    logger.warning(
        "Brief contradicts sealed decision %s: found %r",
        decision.value,
        found,
    )
    return [f"contradiction:{found.lower()}"]
