"""Mission graph construction.

Builds the LangGraph ``StateGraph`` with a conditional edge that skips straight
to reporting when validation fails, and compiles it with the supplied
checkpointer for durable, thread-scoped memory.

``cite_limits`` sits between the calculator and the review step. It attaches
evidence for the limits the assessment used and nothing else: the decision is
already sealed by the time it runs, and retrieval being unavailable leaves the
plan unconfirmed rather than blocked. See ADR-003.

``human_ack`` sits between the calculator and the report, and that order is a
security control rather than a workflow preference: the operator signs an
assessment that no retrieved text and no generated prose has touched. See
ADR-004. Moving ``report`` earlier -- to hide latency behind the review card,
say -- converts a structural guarantee into a filtering problem.
"""

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import (
    make_calculations_node,
    make_cite_limits_node,
    make_human_ack_node,
    make_report_node,
    make_validate_node,
    make_weather_node,
)
from suas.graph.state import MissionState


def route_after_validation(state: MissionState) -> Literal["weather", "report"]:
    """Route to weather when the setup is viable, otherwise straight to report."""
    if state.get("is_viable") is False:
        return "report"
    return "weather"


def route_after_ack(state: MissionState) -> Literal["calculations", "report", "__end__"]:
    """Route on what the operator decided.

    An edit returns to the calculator so the revision is assessed rather than
    assumed. An abort ends the run without ever calling the model.
    """
    action: str = str(state.get("ack_action", "confirm"))
    if action == "edit":
        return "calculations"
    if action == "abort":
        # END is this literal; spelling it out keeps the annotation checkable.
        return "__end__"
    return "report"


def build_mission_graph(
    deps: GraphDependencies,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Return the compiled, checkpointed mission planning graph."""
    builder = StateGraph(MissionState)
    builder.add_node("validate", make_validate_node(deps))
    builder.add_node("weather", make_weather_node(deps))
    builder.add_node("calculations", make_calculations_node(deps))
    builder.add_node("cite_limits", make_cite_limits_node(deps))
    builder.add_node("human_ack", make_human_ack_node())
    builder.add_node("report", make_report_node(deps))

    builder.add_edge(START, "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validation,
        {"weather": "weather", "report": "report"},
    )
    builder.add_edge("weather", "calculations")
    builder.add_edge("calculations", "cite_limits")
    builder.add_edge("cite_limits", "human_ack")
    builder.add_conditional_edges(
        "human_ack",
        route_after_ack,
        {"calculations": "calculations", "report": "report", END: END},
    )
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)
