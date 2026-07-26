"""Request-scoped dependencies."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from suas.api.observability import MetricsRegistry
    from suas.api.ratelimit import SlidingWindowLimiter


def get_graph(request: Request) -> "CompiledStateGraph":
    """Return the compiled mission graph stored on application state."""
    graph: CompiledStateGraph = request.app.state.graph
    return graph


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the database session factory stored on application state."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_metrics(request: Request) -> "MetricsRegistry":
    """Return the metrics registry stored on application state."""
    metrics: MetricsRegistry = request.app.state.metrics
    return metrics


def get_limiter(request: Request) -> "SlidingWindowLimiter":
    """Return the rate limiter stored on application state."""
    limiter: SlidingWindowLimiter = request.app.state.limiter
    return limiter


GraphDep = Annotated["CompiledStateGraph", Depends(get_graph)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
MetricsDep = Annotated["MetricsRegistry", Depends(get_metrics)]
LimiterDep = Annotated["SlidingWindowLimiter", Depends(get_limiter)]
