"""HTTP routes for health and mission planning."""

import logging
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.errors import GraphRecursionError

from suas import __version__
from suas.api.dependencies import GraphDep
from suas.api.security import require_api_key
from suas.schemas.requests import MissionRequest
from suas.schemas.responses import (
    Calculations,
    HealthResponse,
    PlanResponse,
    WeatherReading,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from suas.graph.state import MissionState

logger: Final[logging.Logger] = logging.getLogger(__name__)

router: Final[APIRouter] = APIRouter()


def _build_plan_response(final_state: dict[str, Any], thread_id: str) -> PlanResponse:
    """Convert the graph's final state into a typed API response."""
    weather_dump = final_state.get("weather")
    calc_dump = final_state.get("calculations")
    weather = WeatherReading.model_validate(weather_dump) if weather_dump else None
    calculations = Calculations.model_validate(calc_dump) if calc_dump else None
    return PlanResponse(
        is_viable=bool(final_state.get("is_viable", False)),
        calculations=calculations,
        weather=weather,
        report=str(final_state.get("report", "")),
        thread_id=thread_id,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return a liveness payload."""
    return HealthResponse(status="operational", service="suas-engine", version=__version__)


@router.post("/api/plan", response_model=PlanResponse)
async def plan_mission(
    request: MissionRequest,
    graph: GraphDep,
    _: None = Depends(require_api_key),
) -> PlanResponse:
    """Plan and assess a single mission, returning the go/no-go result."""
    thread_id: str = request.thread_id or str(uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    initial: MissionState = {
        "aircraft_id": request.aircraft_id,
        "payload_id": request.payload_id,
        "mission_params": request.mission_params.model_dump(),
        "is_viable": True,
    }
    try:
        final_state = await graph.ainvoke(initial, config=config)
    except GraphRecursionError as exc:
        logger.error("Graph recursion limit hit for thread %s: %s", thread_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mission orchestration failed",
        ) from exc
    return _build_plan_response(dict(final_state), thread_id)
