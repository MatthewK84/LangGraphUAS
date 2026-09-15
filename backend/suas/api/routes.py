"""HTTP routes for health, readiness, catalog, planning, and metrics."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from langgraph.types import Command
from sqlalchemy import text

from suas import __version__
from suas.api.dependencies import GraphDep, MetricsDep, ReplanGraphDep, SessionFactoryDep
from suas.api.rate_limit_dep import enforce_rate_limit
from suas.api.security import require_api_key
from suas.api.thread_locks import thread_lock
from suas.db.corpus import open_quarantine_configs
from suas.db.flight_logs import apply_flight_log, store_flight_log
from suas.db.repository import list_aircraft, list_payloads
from suas.db.retention import (
    lock_thread_for_update,
    next_replan_thread_id,
    record_acknowledgement,
    record_thread,
)
from suas.schemas.assessment import DeterministicAssessment
from suas.schemas.requests import AckRequest, MissionRequest
from suas.schemas.responses import (
    AircraftSummary,
    Calculations,
    FlightLogResponse,
    HealthResponse,
    LiveEnergyView,
    PayloadSummary,
    PlanResponse,
    PowerEstimateSummary,
    ReadinessResponse,
    ReplanResponse,
    ThreadStateResponse,
    WeatherReading,
)
from suas.schemas.telemetry import TelemetrySnapshot

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from suas.graph.state import MissionState

logger: Final[logging.Logger] = logging.getLogger(__name__)

router: Final[APIRouter] = APIRouter()

_DEGRADED_WEATHER_WARNING: Final[str] = (
    "Weather is {state}, not a live feed. Confirm conditions independently before flight."
)


def _thread_config(thread_id: str) -> "RunnableConfig":
    """Return the LangGraph config that scopes state to one thread."""
    return {"configurable": {"thread_id": thread_id}}


def _collect_warnings(weather: WeatherReading | None) -> list[str]:
    """Return operator-facing warnings about degraded inputs.

    A cached-but-fresh reading is not warned about, because it is good enough to
    fly on. Everything short of that is named explicitly rather than lumped under
    one word: "cached from 40 minutes ago" and "the provider returned nonsense"
    call for different reactions.
    """
    if weather is None or weather.is_operational_grade:
        return []
    return [_DEGRADED_WEATHER_WARNING.format(state=weather.source.value.replace("_", " "))]


def _build_plan_response(final_state: dict[str, Any], thread_id: str) -> PlanResponse:
    """Convert the graph's final state into a typed API response."""
    weather_dump = final_state.get("weather")
    calc_dump = final_state.get("calculations")
    assessment_dump = final_state.get("assessment")
    weather = WeatherReading.model_validate(weather_dump) if weather_dump else None
    calculations = Calculations.model_validate(calc_dump) if calc_dump else None
    assessment = (
        DeterministicAssessment.model_validate(assessment_dump) if assessment_dump else None
    )
    warnings: list[str] = _collect_warnings(weather)
    awaiting: bool = bool(final_state.get("__interrupt__"))
    return PlanResponse(
        awaiting_ack=awaiting,
        aborted=bool(final_state.get("aborted", False)),
        is_viable=assessment.is_viable
        if assessment
        else bool(final_state.get("is_viable", False)),
        assessment=assessment,
        calculations=calculations,
        weather=weather,
        report=str(final_state.get("report", "")),
        thread_id=thread_id,
        degraded=bool(warnings),
        warnings=warnings,
    )


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health_check() -> HealthResponse:
    """Return a liveness payload. Does not touch dependencies."""
    return HealthResponse(status="operational", service="suas-engine", version=__version__)


@router.get("/ready", response_model=ReadinessResponse, tags=["ops"])
async def readiness_check(
    session_factory: SessionFactoryDep,
    response: Response,
) -> ReadinessResponse:
    """Return readiness, verifying the database is actually reachable."""
    database: str = "ok"
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # A probe must report status, never propagate.
        logger.error("Readiness database check failed: %s", exc)
        database = "unavailable"
    ready: bool = database == "ok"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=ready, database=database, checkpointer="ok")


@router.get("/metrics", tags=["ops"])
async def metrics_endpoint(
    metrics: MetricsDep,
    session_factory: SessionFactoryDep,
) -> Response:
    """Return metrics in Prometheus text exposition format.

    The quarantine gauge is read from the database on scrape. Ingest is an
    offline act, so nothing in this process would otherwise know that a document
    had been held back since the last restart.
    """
    async with session_factory() as session:
        metrics.set_quarantine_open(len(await open_quarantine_configs(session)))
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")


@router.get("/api/aircraft", response_model=list[AircraftSummary], tags=["catalog"])
async def get_aircraft_catalog(session_factory: SessionFactoryDep) -> list[AircraftSummary]:
    """Return every selectable airframe. Drives the client dropdown."""
    async with session_factory() as session:
        aircraft = await list_aircraft(session)
    return [AircraftSummary.model_validate(item, from_attributes=True) for item in aircraft]


@router.get("/api/payloads", response_model=list[PayloadSummary], tags=["catalog"])
async def get_payload_catalog(session_factory: SessionFactoryDep) -> list[PayloadSummary]:
    """Return every selectable payload. Drives the client dropdown."""
    async with session_factory() as session:
        payloads = await list_payloads(session)
    return [PayloadSummary.model_validate(item, from_attributes=True) for item in payloads]


@router.post(
    "/api/plan",
    response_model=PlanResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def plan_mission(
    request: MissionRequest,
    graph: GraphDep,
    metrics: MetricsDep,
    session_factory: SessionFactoryDep,
) -> PlanResponse:
    """Plan and assess a single mission, returning the go/no-go result."""
    thread_id: str = request.thread_id or str(uuid4())
    initial: MissionState = {
        "aircraft_id": request.aircraft_id,
        "payload_id": request.payload_id,
        "mission_params": request.mission_params.model_dump(),
        "requested_mode": request.assessment_mode.value,
        "is_viable": True,
    }
    # Recorded before the run so a thread that writes a checkpoint and then
    # fails is still eligible for retention rather than leaking.
    async with session_factory() as session:
        await record_thread(session, thread_id)
    final_state = await graph.ainvoke(initial, config=_thread_config(thread_id), durability="sync")
    result: PlanResponse = _build_plan_response(dict(final_state), thread_id)
    metrics.record_plan(
        is_viable=result.is_viable,
        weather_live=result.weather is None or result.weather.is_live,
    )
    violations = final_state.get("seal_violations")
    if isinstance(violations, list):
        metrics.record_seal_violations(len(violations))
    return result


def _estimate_summary(
    median_w: float | None,
    samples: int | None,
    confidence: str | None,
) -> PowerEstimateSummary | None:
    """Return the response view of a stored estimate, or None when absent."""
    if median_w is None or samples is None:
        return None
    return PowerEstimateSummary(
        median_w=median_w,
        sample_count=samples,
        confidence=confidence or "low",
    )


@router.post(
    "/api/logs",
    response_model=FlightLogResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def upload_flight_log(
    request: Request,
    airframe_id: str,
    session_factory: SessionFactoryDep,
    apply: bool = False,
) -> FlightLogResponse:
    """Ingest a CSV flight log and derive measured power for one airframe.

    The body is the CSV itself. Ingesting always stores and estimates; ``apply``
    additionally writes the estimates into the airframe's reference row, which is
    the only way a measured figure becomes a number plans are built on. It
    defaults to false because that write should be deliberate.
    """
    raw: bytes = await request.body()
    try:
        content: str = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Flight log must be UTF-8 text") from exc

    async with session_factory() as session:
        log_row = await store_flight_log(session, airframe_id=airframe_id, content=content)
        applied: list[str] = await apply_flight_log(session, log_row.log_id) if apply else []

    return FlightLogResponse(
        log_id=log_row.log_id,
        airframe_id=log_row.airframe_id,
        row_count=log_row.row_count,
        rejected_rows=log_row.rejected_rows,
        hover=_estimate_summary(
            log_row.hover_median_w, log_row.hover_samples, log_row.hover_confidence
        ),
        cruise=_estimate_summary(
            log_row.cruise_median_w, log_row.cruise_samples, log_row.cruise_confidence
        ),
        applied_fields=applied,
    )


@router.post(
    "/api/plan/{thread_id}/ack",
    response_model=PlanResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def acknowledge_plan(
    thread_id: str,
    request: AckRequest,
    graph: GraphDep,
    metrics: MetricsDep,
    session_factory: SessionFactoryDep,
) -> PlanResponse:
    """Record an operator's decision on a pending assessment and resume the run.

    Nothing downstream of this runs until it does: the report node sits after the
    review step precisely so a brief cannot exist without a signature.
    """
    # Everything below runs under two locks on this one thread: an in-process
    # mutex, and a row lock on the mission row. Two workers handed the same
    # acknowledgement therefore serialise rather than both resuming the
    # interrupt, and the second to get in finds the graph no longer awaiting and
    # is refused. Both cover one mission and block nothing else.
    async with thread_lock(thread_id), session_factory() as session:
        locked = await lock_thread_for_update(session, thread_id)

        snapshot = await graph.aget_state(_thread_config(thread_id))
        values: dict[str, Any] = dict(snapshot.values) if snapshot and snapshot.values else {}
        if not values:
            raise HTTPException(status_code=404, detail="Unknown planning thread")
        if not (snapshot and snapshot.next):
            raise HTTPException(
                status_code=409, detail="This plan is not awaiting acknowledgement"
            )

        assessment_dump: dict[str, Any] = dict(values.get("assessment") or {})
        current_hash: str = str(assessment_dump.get("inputs_hash", ""))
        if request.inputs_hash and request.inputs_hash != current_hash:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The assessment changed after it was shown. Re-read the plan and "
                    "acknowledge the current one."
                ),
            )

        resume: dict[str, Any] = {
            "action": request.action,
            "actor": request.actor,
            "edits": request.edits.model_dump(exclude_none=True) if request.edits else {},
        }
        final_state = await graph.ainvoke(
            Command(resume=resume), config=_thread_config(thread_id), durability="sync"
        )
        state: dict[str, Any] = dict(final_state)

        # Only a signature that a run actually proceeded on is recorded. An edit
        # produces a new assessment, which is a new thing to sign.
        if request.action == "confirm" and current_hash and locked is not None:
            await record_acknowledgement(
                session,
                thread_id=thread_id,
                actor=request.actor,
                action=request.action,
                inputs_hash=current_hash,
                calculator_version=str(assessment_dump.get("calculator_version", "")),
            )
        elif request.action == "confirm" and locked is None:
            logger.warning("Acknowledged thread %s has no retention row", thread_id)

    violations = state.get("seal_violations")
    if isinstance(violations, list):
        metrics.record_seal_violations(len(violations))
    return _build_plan_response(state, thread_id)


@router.post(
    "/api/replan",
    response_model=ReplanResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def replan_mission(
    snapshot: TelemetrySnapshot,
    graph: GraphDep,
    replan_graph: ReplanGraphDep,
    session_factory: SessionFactoryDep,
) -> ReplanResponse:
    """Compare a briefed plan against what the aircraft is reporting.

    Runs on a child thread of the briefed one, so the assessment an operator
    signed stays addressable and unchanged. No language model is involved: this
    runs while an aircraft is in the air, which is the worst moment to wait on one
    or to let one influence what the operator is told.
    """
    parent = await graph.aget_state(_thread_config(snapshot.thread_id))
    briefed: dict[str, Any] = dict(parent.values) if parent and parent.values else {}
    if not briefed:
        raise HTTPException(status_code=404, detail="Unknown planning thread")

    assessment_dump: dict[str, Any] = dict(briefed.get("assessment") or {})
    if not assessment_dump:
        raise HTTPException(
            status_code=409,
            detail="That thread has no assessment to replan against",
        )

    calculations_dump: dict[str, Any] = dict(briefed.get("calculations") or {})
    battery_check: dict[str, Any] = dict(calculations_dump.get("battery_check") or {})
    briefed_margin_wh = float(battery_check.get("margin_wh", 0.0))
    age_s: float = snapshot.age_s(datetime.now(UTC))

    async with session_factory() as session:
        try:
            child_thread_id: str = await next_replan_thread_id(session, snapshot.thread_id)
        except KeyError:
            # A thread with checkpoints but no retention row predates that table.
            child_thread_id = f"{snapshot.thread_id}:1"

    initial: dict[str, Any] = {
        "snapshot": snapshot.model_dump(mode="json"),
        "aircraft": briefed.get("aircraft"),
        "payload": briefed.get("payload"),
        "briefed_assessment": assessment_dump,
        "briefed_margin_wh": briefed_margin_wh,
        "snapshot_age_s": age_s,
    }
    final = await replan_graph.ainvoke(
        initial, config=_thread_config(child_thread_id), durability="sync"
    )
    state: dict[str, Any] = dict(final)
    energy_dump = state.get("live_energy")

    return ReplanResponse(
        thread_id=child_thread_id,
        parent_thread_id=snapshot.thread_id,
        severity=state.get("severity", "info"),
        recommended_action=state.get("recommended_action", "continue"),
        operational_ok=bool(state.get("operational_ok", False)),
        live_energy=LiveEnergyView.model_validate(energy_dump) if energy_dump else None,
        briefed_margin_wh=briefed_margin_wh,
        snapshot_age_s=round(age_s, 1),
        alerts=state.get("alerts", []),
    )


@router.get(
    "/api/plan/{thread_id}",
    response_model=ThreadStateResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key)],
)
async def get_thread_state(thread_id: str, graph: GraphDep) -> ThreadStateResponse:
    """Return the persisted state for a previously planned mission thread."""
    snapshot = await graph.aget_state(_thread_config(thread_id))
    values: dict[str, Any] = dict(snapshot.values) if snapshot and snapshot.values else {}
    if not values:
        return ThreadStateResponse(
            thread_id=thread_id,
            found=False,
            is_viable=None,
            report=None,
            calculations=None,
            weather=None,
        )
    calc_dump = values.get("calculations")
    weather_dump = values.get("weather")
    assessment_dump = values.get("assessment")
    return ThreadStateResponse(
        thread_id=thread_id,
        found=True,
        is_viable=bool(values.get("is_viable", False)),
        report=str(values.get("report", "")),
        calculations=Calculations.model_validate(calc_dump) if calc_dump else None,
        weather=WeatherReading.model_validate(weather_dump) if weather_dump else None,
        assessment=(
            DeterministicAssessment.model_validate(assessment_dump) if assessment_dump else None
        ),
        # The sealed assessment survives a crash at the review step; this is what
        # tells a returning client the signature is still outstanding.
        awaiting_ack=bool(snapshot and snapshot.next),
    )
