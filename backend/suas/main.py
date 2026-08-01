"""FastAPI application factory and lifespan.

The lifespan owns every long-lived resource: the database engine, the weather
HTTP client, and the checkpointer-backed graph. All are created on startup and
disposed on shutdown so nothing leaks between runs.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
from suas.api.ratelimit import SlidingWindowLimiter
from suas.api.routes import router
from suas.config import Settings, get_settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.retention import purge_expired_threads
from suas.db.seed import seed_reference_data
from suas.graph.checkpointer import build_checkpointer
from suas.graph.dependencies import GraphDependencies
from suas.graph.workflow import build_mission_graph
from suas.logging_config import configure_logging
from suas.services.llm import ReportService
from suas.services.weather import WeatherService

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
    await create_schema(engine)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        await seed_reference_data(session)
    weather_client = httpx.AsyncClient(timeout=settings.weather_timeout_s)
    weather_service = WeatherService(
        client=weather_client,
        base_url=settings.weather_base_url,
        retry_attempts=settings.weather_retry_attempts,
    )
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=weather_service,
        report=ReportService(settings),
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
    """Age out old checkpoints on boot. Never blocks startup on failure."""
    try:
        purged: int = await purge_expired_threads(
            session_factory, checkpointer, settings.checkpoint_retention_days
        )
    except Exception as exc:  # Retention is housekeeping, not a startup gate.
        logger.error("Checkpoint retention pass failed: %s", exc)
        return
    if purged > 0:
        logger.info("Startup retention purged %d expired threads", purged)


async def _dispose_resources(resources: _Resources) -> None:
    """Close all long-lived resources on shutdown."""
    await resources.weather_client.aclose()
    await resources.engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown of all long-lived resources."""
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.json_logs)
    if not settings.auth_enabled:
        logger.warning("API authentication is disabled; set SUAS_API_KEY in production")
    resources = await _build_resources(settings)
    async with build_checkpointer(settings) as checkpointer:
        app.state.graph = build_mission_graph(resources.deps, checkpointer)
        app.state.session_factory = resources.session_factory
        await _purge_checkpoints(resources.session_factory, checkpointer, settings)
        try:
            yield
        finally:
            await _dispose_resources(resources)


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
