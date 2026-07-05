"""Request-scoped dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph


def get_graph(request: Request) -> CompiledStateGraph:
    """Return the compiled mission graph stored on application state."""
    graph: CompiledStateGraph = request.app.state.graph
    return graph


GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]
