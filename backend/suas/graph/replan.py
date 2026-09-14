"""The replan graph.

Five nodes, its own thread, and no language model anywhere in it. A replan runs
while an aircraft is in the air, which is the worst possible moment to wait on a
model or to let one influence what an operator is told. The brief that was signed
stays on the parent thread untouched; this graph only ever reads it.

Its thread is a child of the briefed one (``{parent}:{seq}``), so the original
assessment remains addressable and immutable while each replan gets its own
durable history.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from suas.calculations.battery import DEFAULT_RESERVE_PERCENT
from suas.calculations.replan import LiveEnergy, compute_live_energy, evaluate_replan
from suas.schemas.alerts import Alert, strongest_action, worst_severity
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.telemetry import TelemetrySnapshot

logger: Final[logging.Logger] = logging.getLogger(__name__)


class ReplanState(TypedDict, total=False):
    """State threaded through the replan graph. JSON-native only."""

    # Seeded by the caller from the parent thread and the request.
    snapshot: dict[str, Any]
    aircraft: dict[str, Any]
    payload: dict[str, Any]
    briefed_assessment: dict[str, Any]
    briefed_margin_wh: float
    snapshot_age_s: float

    # Produced by this graph.
    live_energy: dict[str, Any]
    alerts: list[dict[str, Any]]
    severity: str
    recommended_action: str
    operational_ok: bool


@dataclass(frozen=True)
class ReplanDependencies:
    """Collaborators the replan graph needs. Deliberately few."""

    battery_reserve_percent: float = DEFAULT_RESERVE_PERCENT


ReplanNode = Callable[[ReplanState], Awaitable[ReplanState]]


def make_ingest_node() -> ReplanNode:
    """Return a node that validates the incoming snapshot."""

    async def ingest_telemetry(state: ReplanState) -> ReplanState:
        snapshot = TelemetrySnapshot.model_validate(state["snapshot"])
        # Re-dumped after validation so downstream nodes read a normalised shape
        # rather than whatever the client happened to send.
        return {"snapshot": snapshot.model_dump(mode="json")}

    return ingest_telemetry


def make_merge_node() -> ReplanNode:
    """Return a node that pins the briefed figures this replan is measured against."""

    async def merge_briefed_state(state: ReplanState) -> ReplanState:
        assessment: dict[str, Any] = dict(state.get("briefed_assessment") or {})
        if not assessment:
            logger.warning("Replan running without a briefed assessment to compare against")
        return {"briefed_assessment": assessment}

    return merge_briefed_state


def make_recalculate_node(deps: ReplanDependencies) -> ReplanNode:
    """Return a node that recomputes the energy picture from live telemetry."""

    async def recalculate(state: ReplanState) -> ReplanState:
        live: LiveEnergy = compute_live_energy(
            aircraft=Aircraft.model_validate(state["aircraft"]),
            payload=Payload.model_validate(state["payload"]),
            snapshot=TelemetrySnapshot.model_validate(state["snapshot"]),
            reserve_percent=deps.battery_reserve_percent,
        )
        return {"live_energy": _energy_dump(live)}

    return recalculate


def make_compare_node(deps: ReplanDependencies) -> ReplanNode:
    """Return a node that compares briefed against live and raises alerts."""

    async def compare(state: ReplanState) -> ReplanState:
        _, alerts = evaluate_replan(
            aircraft=Aircraft.model_validate(state["aircraft"]),
            payload=Payload.model_validate(state["payload"]),
            snapshot=TelemetrySnapshot.model_validate(state["snapshot"]),
            briefed_margin_wh=float(state.get("briefed_margin_wh", 0.0)),
            reserve_percent=deps.battery_reserve_percent,
            age_s=float(state.get("snapshot_age_s", 0.0)),
        )
        return {"alerts": [alert.model_dump(mode="json") for alert in alerts]}

    return compare


def make_alert_node() -> ReplanNode:
    """Return a node that reduces the alerts to one severity and one action."""

    async def alert(state: ReplanState) -> ReplanState:
        alerts: list[Alert] = [
            Alert.model_validate(item) for item in state.get("alerts", []) or []
        ]
        severity = worst_severity(alerts)
        action = strongest_action(alerts)
        # A replan carries operational weight only when nothing is outstanding.
        # Any alert at all, including a watch, means something could not be
        # confirmed, and an unconfirmed replan is advice.
        return {
            "severity": severity.value,
            "recommended_action": action.value,
            "operational_ok": not alerts,
        }

    return alert


def _energy_dump(live: LiveEnergy) -> dict[str, Any]:
    """Return the JSON-native view of a live energy picture."""
    return {
        "available_wh": live.available_wh,
        "reserve_wh": live.reserve_wh,
        "required_wh": live.required_wh,
        "residual_wh": live.residual_wh,
        "temperature_factor": live.temperature_factor,
    }


def build_replan_graph(
    deps: ReplanDependencies,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Return the compiled, checkpointed replan graph."""
    builder = StateGraph(ReplanState)
    builder.add_node("ingest_telemetry", make_ingest_node())
    builder.add_node("merge_briefed_state", make_merge_node())
    builder.add_node("recalculate", make_recalculate_node(deps))
    builder.add_node("compare", make_compare_node(deps))
    builder.add_node("alert", make_alert_node())

    builder.add_edge(START, "ingest_telemetry")
    builder.add_edge("ingest_telemetry", "merge_briefed_state")
    builder.add_edge("merge_briefed_state", "recalculate")
    builder.add_edge("recalculate", "compare")
    builder.add_edge("compare", "alert")
    builder.add_edge("alert", END)

    return builder.compile(checkpointer=checkpointer)
