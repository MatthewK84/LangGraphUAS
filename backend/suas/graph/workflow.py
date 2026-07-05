"""Mission graph construction.

Builds the LangGraph ``StateGraph`` with a conditional edge that skips straight
to reporting when validation fails, and compiles it with the supplied
checkpointer for durable, thread-scoped memory.
"""

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import (
    make_calculations_node,
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


def build_mission_graph(
    deps: GraphDependencies,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Return the compiled, checkpointed mission planning graph."""
    builder = StateGraph(MissionState)
    builder.add_node("validate", make_validate_node(deps))
    builder.add_node("weather", make_weather_node(deps))
    builder.add_node("calculations", make_calculations_node())
    builder.add_node("report", make_report_node(deps))

    builder.add_edge(START, "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validation,
        {"weather": "weather", "report": "report"},
    )
    builder.add_edge("weather", "calculations")
    builder.add_edge("calculations", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer)
