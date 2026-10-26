"""FastAPI application factory and lifespan.

The lifespan owns every long-lived resource: the database engine, the weather
HTTP client, and the checkpointer-backed graph. All are created on startup and
disposed on shutdown so nothing leaks between runs.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, Final

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from suas import __version__
from suas.api.exception_handlers import register_exception_handlers
from suas.api.observability import MetricsRegistry, RequestContextMiddleware
from suas.api.ratelimit import SlidingWindowLimiter, build_limiter, prune_idle_buckets
from suas.api.routes import router
from suas.config import DEMO_SESSION_KEY_SECRET, Settings, describe_database_url, get_settings
from suas.db.engine import (
    SchemaNotMigratedError,
    create_engine,
    create_session_factory,
    prepare_schema,
)
from suas.db.retention import purge_expired_threads
from suas.db.seed import seed_reference_data
from suas.graph.checkpointer import build_checkpointer
from suas.graph.dependencies import GraphDependencies
from suas.graph.replan import ReplanDependencies, build_replan_graph
from suas.graph.workflow import build_mission_graph
from suas.logging_config import configure_logging
from suas.rag.provider import build_embedder
from suas.services.llm import ReportService
from suas.services.weather import build_weather_service, prune_stale_weather
from suas.tracing import build_tracing, refuse_unredacted_tracing, trace_graph

logger: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass
class _Resources:
    """Long-lived resources owned by the application lifespan."""

    engine: AsyncEngine
    weather_client: httpx.AsyncClient
    deps: GraphDependencies
    session_factory: async_sessionmaker[AsyncSession]


async def _build_resources(settings: Settings) -> _Resources:
    """Create the engine, schema, seed data, service clients, and dependencies."""
    engine = create_engine(settings.database_url)
    try:
        await prepare_schema(engine, alembic_owns_schema=settings.require_postgres)
    except SchemaNotMigratedError:
        await engine.dispose()
        raise
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        await seed_reference_data(session)
    weather_client = httpx.AsyncClient(timeout=settings.weather_timeout_s)
    weather_service = build_weather_service(settings, weather_client, session_factory)
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=weather_service,
        report=ReportService(settings),
        # Retrieval shares the HTTP client with weather. The embedding model
        # lives wherever configuration says: in this process as a lexical
        # hash, or behind a URL as a service of its own.
        embedder=build_embedder(settings, weather_client),
        battery_reserve_percent=settings.battery_reserve_percent,
        vertical_speed_mps=settings.vertical_speed_mps,
        climb_efficiency=settings.climb_efficiency,
    )
    return _Resources(
        engine=engine,
        weather_client=weather_client,
        deps=deps,
        session_factory=session_factory,
    )


async def _purge_checkpoints(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    settings: Settings,
) -> None:
    """Age out old checkpoints. Never raises: retention is housekeeping, not a gate.

    Every worker runs this; ``purge_expired_threads`` claims each thread by
    deleting its row, so concurrent passes purge each thread once.
    """
    try:
        purged: int = await purge_expired_threads(
            session_factory, checkpointer, settings.checkpoint_retention_days
        )
    except Exception as exc:  # Retention is housekeeping, not a startup gate.
        logger.error("Checkpoint retention pass failed: %s", exc)
        return
    if purged > 0:
        logger.info("Retention purged %d expired threads", purged)


async def _prune_rate_limit_buckets(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Drop shared rate-limit rows with no hit left in the window. Never raises."""
    try:
        pruned: int = await prune_idle_buckets(session_factory, settings.rate_limit_window_s)
    except Exception as exc:  # Housekeeping, like retention.
        logger.error("Rate-limit pruning pass failed: %s", exc)
        return
    if pruned > 0:
        logger.info("Pruned %d idle rate-limit buckets", pruned)


async def _prune_weather_cache(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Drop shared weather readings past the stale max age. Never raises."""
    try:
        pruned: int = await prune_stale_weather(session_factory, settings.weather_stale_max_age_s)
    except Exception as exc:  # Housekeeping, like retention.
        logger.error("Weather cache pruning pass failed: %s", exc)
        return
    if pruned > 0:
        logger.info("Pruned %d expired weather readings", pruned)


async def _housekeep(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    settings: Settings,
) -> None:
    """Run one retention pass over everything that ages out."""
    await _purge_checkpoints(session_factory, checkpointer, settings)
    await _prune_rate_limit_buckets(session_factory, settings)
    await _prune_weather_cache(session_factory, settings)


async def _housekeep_forever(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    settings: Settings,
) -> None:
    """Repeat retention every ``retention_interval_s`` until cancelled at shutdown."""
    while True:
        await asyncio.sleep(settings.retention_interval_s)
        await _housekeep(session_factory, checkpointer, settings)


async def _dispose_resources(resources: _Resources) -> None:
    """Close all long-lived resources on shutdown."""
    await resources.weather_client.aclose()
    await resources.engine.dispose()


def warn_on_weak_auth(settings: Settings) -> None:
    """Say at startup, by name, when authentication protects nothing."""
    if not settings.auth_enabled:
        logger.warning("API authentication is disabled; set SUAS_API_KEY in production")
    if settings.session_key_secret == DEMO_SESSION_KEY_SECRET:
        logger.warning(
            "DEMO session secret in use: anyone can mint any browser's key. "
            "Set SUAS_SESSION_KEY_SECRET to a private value before exposing this deployment"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of all long-lived resources."""
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.json_logs)
    warn_on_weak_auth(settings)
    refuse_unredacted_tracing(os.environ)
    tracing = build_tracing(settings)
    logger.info("Database: %s", describe_database_url(settings.database_url))
    if not settings.uses_postgres:
        # Reaching this in a deployment means SUAS_DATABASE_URL never arrived and
        # the built-in default was used. The container filesystem is ephemeral
        # and, for a non-root user, largely unwritable -- so this either loses
        # every plan on restart or fails to open the file at all, and the
        # traceback for the second one names sqlite3, never the missing variable.
        logger.warning(
            "Not using PostgreSQL. If this is a deployment, SUAS_DATABASE_URL is "
            "unset and this database is ephemeral; set it to the Postgres service URL."
        )
    resources = await _build_resources(settings)
    async with build_checkpointer(settings) as checkpointer:
        app.state.graph = trace_graph(build_mission_graph(resources.deps, checkpointer), tracing)
        # Same checkpointer: a replan is a child thread of the briefed one, so
        # both live in one durable store and age out under one retention policy.
        app.state.replan_graph = trace_graph(
            build_replan_graph(
                ReplanDependencies(battery_reserve_percent=resources.deps.battery_reserve_percent),
                checkpointer,
            ),
            tracing,
        )
        app.state.session_factory = resources.session_factory
        app.state.limiter = build_limiter(settings, resources.session_factory)
        await _housekeep(resources.session_factory, checkpointer, settings)
        # Startup's pass alone left a long-lived process never purging (#86).
        housekeeping = asyncio.create_task(
            _housekeep_forever(resources.session_factory, checkpointer, settings),
            name="suas-housekeeping",
        )
        try:
            yield
        finally:
            housekeeping.cancel()
            with suppress(asyncio.CancelledError):
                await housekeeping
            await _dispose_resources(resources)
            tracing.flush()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="sUAS Mission Planning API",
        description="Async LangGraph orchestration with durable checkpointing.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    metrics = MetricsRegistry()
    app.state.metrics = metrics
    app.state.limiter = SlidingWindowLimiter(
        max_requests=settings.rate_limit_requests,
        window_s=settings.rate_limit_window_s,
    )
    app.add_middleware(RequestContextMiddleware, metrics=metrics)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app: Final[FastAPI] = create_app()
