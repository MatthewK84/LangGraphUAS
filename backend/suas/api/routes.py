"""HTTP routes for health, readiness, catalog, planning, and metrics."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from langgraph.types import Command, StateSnapshot
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas import __version__
from suas.api.dependencies import GraphDep, MetricsDep, ReplanGraphDep, SessionFactoryDep
from suas.api.number_provenance import number_provenance
from suas.api.observability import MetricsRegistry
from suas.api.rate_limit_dep import enforce_rate_limit
from suas.api.security import OperatorDep, require_api_key
from suas.api.thread_locks import contended_waits, thread_lock
from suas.db.corpus import open_quarantine_configs
from suas.db.flight_logs import apply_flight_log, store_flight_log
from suas.db.migrations import MigrationState, migration_state
from suas.db.repository import list_aircraft, list_payloads
from suas.db.retention import (
    lock_thread_for_update,
    next_replan_thread_id,
    record_acknowledgement,
    record_thread,
    thread_owner,
)
from suas.logging_config import annotate_trace
from suas.schemas.assessment import AssessmentMode, DeterministicAssessment
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import AckRequest, MissionRequest
from suas.schemas.responses import (
    AircraftSummary,
    Calculations,
    FlightLogResponse,
    HealthResponse,
    LiveEnergyView,
    NumberProvenance,
    PayloadSummary,
    PlanResponse,
    PowerEstimateSummary,
    ReadinessResponse,
    ReplanResponse,
    ThreadStateResponse,
    WeatherReading,
)
from suas.schemas.telemetry import TelemetrySnapshot
from suas.schemas.thread_ids import MAX_THREAD_ID_LENGTH

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


def _state_values(snapshot: StateSnapshot | None) -> dict[str, Any]:
    """Return a thread's stored values, or an empty dict for an unknown thread."""
    return dict(snapshot.values) if snapshot and snapshot.values else {}


def _sub_dict(values: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``values[key]`` as a dict, treating a missing or empty entry as ``{}``."""
    return dict(values.get(key) or {})


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


def _figure_provenance(values: dict[str, Any]) -> dict[str, NumberProvenance]:
    """Return what each W and Wh figure rests on, or ``{}`` when nothing was calculated."""
    aircraft, payload = values.get("aircraft"), values.get("payload")
    if not (values.get("calculations") and aircraft and payload):
        return {}
    return number_provenance(Aircraft.model_validate(aircraft), Payload.model_validate(payload))


_UNKNOWN_THREAD: Final[str] = "Unknown planning thread"
# Looked up, not created, so lenient: ids stored before the format still work.
ThreadIdPath = Annotated[str, Path(max_length=MAX_THREAD_ID_LENGTH)]


async def _owner_of(
    session_factory: async_sessionmaker[AsyncSession], thread_id: str
) -> tuple[bool, str | None]:
    """Return whether the thread has a mission row, and whose key planned it."""
    async with session_factory() as session:
        return await thread_owner(session, thread_id)


async def _visible_to(
    session_factory: async_sessionmaker[AsyncSession], thread_id: str, operator: str | None
) -> bool:
    """Return whether this operator may see the thread at all.

    With auth off there are no operators to separate. With it on, a thread is
    visible only to the key that planned it; one with no mission row, or planned
    with auth off, belongs to nobody and is visible to no key.
    """
    if operator is None:
        return True
    known, owner = await _owner_of(session_factory, thread_id)
    return known and owner == operator


async def _require_visible(
    session_factory: async_sessionmaker[AsyncSession], thread_id: str, operator: str | None
) -> None:
    """Refuse another operator's thread exactly as an unknown one is refused (#81)."""
    if not await _visible_to(session_factory, thread_id, operator):
        raise HTTPException(status_code=404, detail=_UNKNOWN_THREAD)


async def _require_claimable(
    session_factory: async_sessionmaker[AsyncSession], thread_id: str, operator: str | None
) -> None:
    """Refuse to plan onto a thread id another operator already holds.

    A new id is free to take. An id another key planned is refused as unknown,
    which tells the caller only that the id is taken, never what is in it.
    """
    if operator is None:
        return
    known, owner = await _owner_of(session_factory, thread_id)
    if known and owner != operator:
        raise HTTPException(status_code=404, detail=_UNKNOWN_THREAD)


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
        provenance=_figure_provenance(final_state),
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


_READINESS_PROBE_THREAD: str = "__readiness_probe__"


async def _database_states(session_factory: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    """Return (database, migrations). Migrations are ``unknown`` when the database is down."""
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
            tracked_required = session.get_bind().dialect.name != "sqlite"
            migrations = await migration_state(session, tracked_required=tracked_required)
    except Exception as exc:  # A probe must report status, never propagate.
        logger.error("Readiness database check failed: %s", exc)
        return "unavailable", "unknown"
    return "ok", migrations.value


async def _checkpointer_state(graph: Any) -> str:
    """Read one (absent) checkpoint, proving the plan store answers."""
    try:
        await graph.checkpointer.aget_tuple(_thread_config(_READINESS_PROBE_THREAD))
    except Exception as exc:  # A probe must report status, never propagate.
        logger.error("Readiness checkpointer check failed: %s", exc)
        return "unavailable"
    return "ok"


@router.get("/ready", response_model=ReadinessResponse, tags=["ops"])
async def readiness_check(
    session_factory: SessionFactoryDep,
    graph: GraphDep,
    response: Response,
) -> ReadinessResponse:
    """Return readiness: database reachable, schema at the code's revision, checkpoints readable.

    A missing model key does not count; advisory briefs are a supported mode.
    """
    database, migrations = await _database_states(session_factory)
    checkpointer = await _checkpointer_state(graph)
    ready = (
        database == "ok"
        and migrations in {MigrationState.OK, MigrationState.NOT_TRACKED}
        and checkpointer == "ok"
    )
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        ready=ready, database=database, migrations=migrations, checkpointer=checkpointer
    )


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
    metrics.set_lock_contention("thread", contended_waits())
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
    operator: OperatorDep,
) -> PlanResponse:
    """Plan and assess a single mission, returning the go/no-go result."""
    thread_id: str = request.thread_id or str(uuid4())
    await _require_claimable(session_factory, thread_id, operator)
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
        await record_thread(session, thread_id, operator)
    final_state = await graph.ainvoke(initial, config=_thread_config(thread_id), durability="sync")
    result: PlanResponse = _build_plan_response(dict(final_state), thread_id)
    metrics.record_plan(
        is_viable=result.is_viable,
        mode=_granted_mode(result),
        weather_source=result.weather.source.value if result.weather else "none",
    )
    _record_violations(metrics, final_state.get("seal_violations"))
    return result


def _granted_mode(result: PlanResponse) -> str:
    """Return the mode the gate granted; a plan with no assessment is advisory."""
    assessment = result.assessment
    return (assessment.mode if assessment else AssessmentMode.ADVISORY).value


def _record_violations(metrics: MetricsRegistry, violations: object) -> None:
    """Record seal violations, split by the reason encoded in each code.

    Codes are "<reason>:<detail>". The reason is what an operator needs: a
    contradiction and an invented number are both suppressions, but one suggests
    an injected document and the other a model writing from memory.
    """
    if not isinstance(violations, list):
        return
    metrics.record_seal_violations(len(violations))
    for code in violations:
        reason: str = str(code).partition(":")[0] or "unknown"
        metrics.record_brief_suppressed(reason)


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


def _require_awaiting_ack(snapshot: StateSnapshot | None) -> dict[str, Any]:
    """Return the thread's values, or refuse an unknown or already-resumed thread."""
    values = _state_values(snapshot)
    if not values:
        raise HTTPException(status_code=404, detail=_UNKNOWN_THREAD)
    if not (snapshot and snapshot.next):
        raise HTTPException(status_code=409, detail="This plan is not awaiting acknowledgement")
    return values


def _require_current_hash(assessment_dump: dict[str, Any], requested_hash: str | None) -> str:
    """Return the assessment's hash, refusing a signature on one that has changed.

    The check applies only when the caller sends the hash it was shown.
    """
    current_hash = str(assessment_dump.get("inputs_hash", ""))
    if requested_hash and requested_hash != current_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                "The assessment changed after it was shown. Re-read the plan and "
                "acknowledge the current one."
            ),
        )
    return current_hash


def _resume_payload(request: AckRequest) -> dict[str, Any]:
    """Return the value the review step's interrupt resumes with."""
    return {
        "action": request.action,
        "actor": request.actor,
        "edits": request.edits.model_dump(exclude_none=True) if request.edits else {},
    }


async def _record_signature(
    session: AsyncSession,
    thread_id: str,
    request: AckRequest,
    *,
    assessment_dump: dict[str, Any],
    current_hash: str,
    has_retention_row: bool,
) -> None:
    """Record a confirmed signature against the thread's retention row.

    Only a signature that a run actually proceeded on is recorded. An edit
    produces a new assessment, which is a new thing to sign.
    """
    if request.action != "confirm":
        return
    if not has_retention_row:
        logger.warning("Acknowledged thread %s has no retention row", thread_id)
        return
    if current_hash:
        await record_acknowledgement(
            session,
            thread_id=thread_id,
            actor=request.actor,
            action=request.action,
            inputs_hash=current_hash,
            calculator_version=str(assessment_dump.get("calculator_version", "")),
        )


@router.post(
    "/api/plan/{thread_id}/ack",
    response_model=PlanResponse,
    tags=["planning"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def acknowledge_plan(
    thread_id: ThreadIdPath,
    request: AckRequest,
    graph: GraphDep,
    metrics: MetricsDep,
    session_factory: SessionFactoryDep,
    operator: OperatorDep,
) -> PlanResponse:
    """Record an operator's decision on a pending assessment and resume the run.

    Nothing downstream of this runs until it does: the report node sits after the
    review step precisely so a brief cannot exist without a signature.
    """
    await _require_visible(session_factory, thread_id, operator)
    # Everything below runs under two locks on this one thread: an in-process
    # mutex, and a row lock on the mission row. Two workers handed the same
    # acknowledgement therefore serialise rather than both resuming the
    # interrupt, and the second to get in finds the graph no longer awaiting and
    # is refused. Both cover one mission and block nothing else.
    async with thread_lock(thread_id), session_factory() as session:
        locked = await lock_thread_for_update(session, thread_id)

        snapshot = await graph.aget_state(_thread_config(thread_id))
        values = _require_awaiting_ack(snapshot)
        assessment_dump = _sub_dict(values, "assessment")
        _trace_signed_run(values, assessment_dump)
        current_hash = _require_current_hash(assessment_dump, request.inputs_hash)

        final_state = await graph.ainvoke(
            Command(resume=_resume_payload(request)),
            config=_thread_config(thread_id),
            durability="sync",
        )
        state: dict[str, Any] = dict(final_state)
        await _record_signature(
            session,
            thread_id,
            request,
            assessment_dump=assessment_dump,
            current_hash=current_hash,
            has_retention_row=locked is not None,
        )

    _record_violations(metrics, state.get("seal_violations"))
    return _build_plan_response(state, thread_id)


def _trace_signed_run(values: dict[str, Any], assessment_dump: dict[str, Any]) -> None:
    """Carry the paused run's weather and granted mode onto the ack's log lines.

    The nodes that set them ran in the plan request; the resume does not rerun them.
    """
    weather = _sub_dict(values, "weather")
    annotate_trace(
        weather_source=str(weather.get("source", "-")),
        assessment_mode=str(assessment_dump.get("mode", "-")),
    )


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
    operator: OperatorDep,
) -> ReplanResponse:
    """Compare a briefed plan against what the aircraft is reporting.

    Runs on a child thread of the briefed one, so the assessment an operator
    signed stays addressable and unchanged. No language model is involved: this
    runs while an aircraft is in the air, which is the worst moment to wait on one
    or to let one influence what the operator is told.
    """
    await _require_visible(session_factory, snapshot.thread_id, operator)
    parent = await graph.aget_state(_thread_config(snapshot.thread_id))
    briefed = _state_values(parent)
    if not briefed:
        raise HTTPException(status_code=404, detail=_UNKNOWN_THREAD)

    assessment_dump = _sub_dict(briefed, "assessment")
    if not assessment_dump:
        raise HTTPException(
            status_code=409,
            detail="That thread has no assessment to replan against",
        )

    battery_check = _sub_dict(_sub_dict(briefed, "calculations"), "battery_check")
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
async def get_thread_state(
    thread_id: ThreadIdPath,
    graph: GraphDep,
    session_factory: SessionFactoryDep,
    operator: OperatorDep,
) -> ThreadStateResponse:
    """Return the persisted state for a previously planned mission thread.

    Another operator's thread reads exactly as one that was never planned.
    """
    visible = await _visible_to(session_factory, thread_id, operator)
    snapshot = await graph.aget_state(_thread_config(thread_id)) if visible else None
    values = _state_values(snapshot)
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
        provenance=_figure_provenance(values),
        weather=WeatherReading.model_validate(weather_dump) if weather_dump else None,
        assessment=(
            DeterministicAssessment.model_validate(assessment_dump) if assessment_dump else None
        ),
        # The sealed assessment survives a crash at the review step; this is what
        # tells a returning client the signature is still outstanding.
        awaiting_ack=bool(snapshot and snapshot.next),
    )
