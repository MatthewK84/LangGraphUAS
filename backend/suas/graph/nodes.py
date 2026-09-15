"""Graph nodes.

Each node is produced by a factory that closes over its dependencies, so nodes
carry no global state and are individually testable. Nodes return only the state
keys they update, which LangGraph merges into the running state.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Final

from langgraph.types import interrupt

from suas.calculations.assessment import (
    assess_mission,
    build_assessment,
    insufficient_data_assessment,
    is_mission_viable,
)
from suas.db.corpus import has_open_quarantine
from suas.db.repository import get_aircraft, get_payload
from suas.errors import ReportGenerationError
from suas.graph.dependencies import GraphDependencies
from suas.graph.seal import find_contradiction, render_template_brief
from suas.graph.state import MissionState
from suas.schemas.assessment import AssessmentMode, DeterministicAssessment
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
        # Paperwork containing something that reads as an instruction to a model
        # is not paperwork to fly on until a person has looked at it.
        async with deps.session_factory() as session:
            quarantined: bool = await has_open_quarantine(session, aircraft.id)

        requested_mode = AssessmentMode(
            str(state.get("requested_mode", AssessmentMode.ADVISORY.value))
        )
        assessment: DeterministicAssessment = build_assessment(
            calculations=calculations,
            requested_mode=requested_mode,
            weather=weather,
            aircraft=aircraft,
            payload=payload,
            corpus_quarantined=quarantined,
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
        report, violations = _vet_prose(report, state)
        return {"report": report, "seal_violations": violations}

    return generate_report


def _vet_prose(report: str, state: MissionState) -> tuple[str, list[str]]:
    """Return the brief to publish and any seal violations found in it.

    A brief that contradicts the sealed decision is replaced with one rendered
    from the assessment itself, not truncated: silent truncation hides an attack
    or a bug in progress, while a template keeps the operator informed and makes
    the substitution obvious.
    """
    assessment_dump = state.get("assessment")
    if assessment_dump is None:
        return report, []
    assessment = DeterministicAssessment.model_validate(assessment_dump)
    found: str | None = find_contradiction(report, assessment.decision)
    if found is None:
        return report, []
    logger.warning(
        "Brief contradicts sealed decision %s: found %r. Substituting template.",
        assessment.decision.value,
        found,
    )
    return render_template_brief(assessment), [f"contradiction:{found.lower()}"]


# An operator may revise and re-review, but not forever. The loop exists so a
# mistyped altitude can be fixed without replanning from scratch; an unbounded
# one is a way to spin the graph, and a way for a client bug to spin it silently.
MAX_ACK_ROUNDS: Final[int] = 5


def make_human_ack_node() -> NodeFn:
    """Return a node that pauses for a human to sign off on the assessment.

    This node is the reason a brief can be trusted: it runs after the calculator
    and before the model, so what the operator signs has been touched by neither
    retrieved text nor generated prose. See ADR-004 -- the ordering is a security
    control, not a UX preference.
    """

    async def await_acknowledgement(state: MissionState) -> MissionState:
        rounds: int = int(state.get("ack_rounds", 0))
        if rounds >= MAX_ACK_ROUNDS:
            logger.warning("Acknowledgement round limit reached; proceeding to report")
            return {"ack_action": "confirm", "ack_rounds": rounds}

        response: dict[str, Any] = interrupt(
            {
                "assessment": state.get("assessment"),
                "calculations": state.get("calculations"),
                "weather": state.get("weather"),
                "requested_mode": state.get("requested_mode"),
                "editable": ["target_altitude_m", "hover_time_s", "payload_id"],
                "round": rounds,
            }
        )

        action: str = str(response.get("action", "confirm"))
        updates: MissionState = {
            "ack_action": action,
            "ack_actor": str(response.get("actor", "unknown")),
            "ack_rounds": rounds + 1,
        }
        if action == "abort":
            updates["aborted"] = True
            updates["report"] = "Mission aborted by the operator before any brief was generated."
            return updates
        if action == "edit":
            updates.update(_apply_edits(state, response.get("edits") or {}))
        return updates

    return await_acknowledgement


def _apply_edits(state: MissionState, edits: dict[str, Any]) -> MissionState:
    """Return the state changes for an operator revision.

    Only the fields the interrupt offered are honoured. An edit to anything else
    is ignored rather than merged, so a client cannot quietly rewrite the mission
    between the assessment and the signature.
    """
    updates: MissionState = {}
    params: dict[str, Any] = dict(state.get("mission_params") or {})
    changed: bool = False
    for field in ("target_altitude_m", "hover_time_s"):
        if field in edits and edits[field] is not None:
            params[field] = float(edits[field])
            changed = True
    if changed:
        updates["mission_params"] = params
    payload_id = edits.get("payload_id")
    if payload_id:
        updates["payload_id"] = str(payload_id)
    return updates
