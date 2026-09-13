"""Integration tests for the compiled mission graph."""

from collections.abc import Callable
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from suas.schemas.responses import WeatherReading


def _mission_input(aircraft_id: str = "Skydio_X10D") -> dict[str, Any]:
    return {
        "aircraft_id": aircraft_id,
        "payload_id": "None",
        "mission_params": {
            "distance_m": 2000.0,
            "hover_time_s": 120.0,
            "target_altitude_m": 120.0,
            "elevation_m": 0.0,
            "latitude": 34.0,
            "longitude": -80.0,
        },
        "is_viable": True,
    }


async def test_graph_valid_mission_pauses_before_the_brief(graph: CompiledStateGraph) -> None:
    """The run stops at the review step with the assessment ready and no brief.

    This is the contract the acknowledgement exists to create: the numbers are
    computed and durable, and nothing has been written about them yet.
    """
    config = {"configurable": {"thread_id": "test-valid"}}
    result = await graph.ainvoke(_mission_input(), config=config)
    assert result.get("report") is None
    assert result["weather"] is not None
    assert result["calculations"] is not None
    assert result["assessment"] is not None
    assert isinstance(result["is_viable"], bool)


async def test_graph_produces_the_brief_once_acknowledged(graph: CompiledStateGraph) -> None:
    config = {"configurable": {"thread_id": "test-ack"}}
    await graph.ainvoke(_mission_input(), config=config)
    result = await graph.ainvoke(
        Command(resume={"action": "confirm", "actor": "tester"}), config=config
    )
    assert result["report"] == "TEST REPORT"
    assert result["ack_actor"] == "tester"


async def test_graph_abort_never_generates_a_brief(graph: CompiledStateGraph) -> None:
    config = {"configurable": {"thread_id": "test-abort"}}
    await graph.ainvoke(_mission_input(), config=config)
    result = await graph.ainvoke(
        Command(resume={"action": "abort", "actor": "tester"}), config=config
    )
    assert result["aborted"] is True
    assert "aborted" in result["report"].lower()
    assert "TEST REPORT" not in result["report"]


async def test_graph_edit_reassesses_and_changes_the_hash(
    graph: CompiledStateGraph,
) -> None:
    """An edited mission is assessed again, so the old signature cannot apply."""
    config = {"configurable": {"thread_id": "test-edit"}}
    first = await graph.ainvoke(_mission_input(), config=config)
    original_hash = first["assessment"]["inputs_hash"]

    await graph.ainvoke(
        Command(
            resume={
                "action": "edit",
                "actor": "tester",
                "edits": {"hover_time_s": 900.0},
            }
        ),
        config=config,
    )
    state = await graph.aget_state(config)
    assert state.values["assessment"]["inputs_hash"] != original_hash
    assert state.values["mission_params"]["hover_time_s"] == 900.0
    # Paused again: a revision is a new thing to sign, not a signed thing.
    assert state.next


async def test_graph_invalid_aircraft_routes_to_report(graph: CompiledStateGraph) -> None:
    config = {"configurable": {"thread_id": "test-invalid"}}
    result = await graph.ainvoke(_mission_input("NOT_A_REAL_AIRCRAFT"), config=config)
    assert result["is_viable"] is False
    assert "FATAL" in result["report"]
    assert result.get("weather") is None


async def test_graph_high_wind_is_no_go(
    build_graph: Callable[[WeatherReading], CompiledStateGraph],
) -> None:
    gusty = WeatherReading(
        temperature_c=15.0,
        wind_speed_mps=25.0,
        wind_direction=200.0,
        humidity_percent=60.0,
        conditions="gusty",
    )
    graph = build_graph(gusty)
    config = {"configurable": {"thread_id": "test-wind"}}
    result = await graph.ainvoke(_mission_input(), config=config)
    assert result["is_viable"] is False
    assert result["calculations"]["safety_flags"]["wind_within_limits"] is False
