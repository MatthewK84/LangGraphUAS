from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver  # ADDED: Checkpointer
from backend.models.state import MissionState
from backend.graph.nodes import validate_inputs, fetch_weather_node, calculate_performance, generate_report

def route_after_validation(state: MissionState) -> str:
    """ADDED: Conditional Edge Router logic.
    If the mission fails basic validation (e.g., missing aircraft), skip to report.
    """
    if state.get("is_viable") is False:
        return "report"
    return "weather"

def create_mission_graph():
    workflow = StateGraph(MissionState)
    
    # Add Nodes
    workflow.add_node("validate", validate_inputs)
    workflow.add_node("weather", fetch_weather_node)
    workflow.add_node("calculations", calculate_performance)
    workflow.add_node("report", generate_report)
    
    # Entry Point
    workflow.set_entry_point("validate")
    
    # ADDED: Conditional Edges
    workflow.add_conditional_edges(
        "validate",
        route_after_validation,
        {
            "weather": "weather",
            "report": "report"
        }
    )
    
    # Remaining Edges
    workflow.add_edge("weather", "calculations")
    workflow.add_edge("calculations", "report")
    workflow.add_edge("report", END)
    
    # ADDED: Compile with Checkpointer (Memory)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)

mission_graph = create_mission_graph()
