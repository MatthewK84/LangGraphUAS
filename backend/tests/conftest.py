"""Shared pytest fixtures.

Everything here is hermetic: an in-memory SQLite database seeded from the
bundled reference data, fake weather and report services, and an in-memory
checkpointer. No network calls occur during tests.
"""

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from suas.db.models import AircraftRow, Base, PayloadRow
from suas.graph.dependencies import GraphDependencies
from suas.graph.workflow import build_mission_graph
from suas.schemas.responses import WeatherReading

_DATA_DIR = Path(__file__).resolve().parent.parent / "suas" / "data"

CALM_WEATHER = WeatherReading(
    temperature_c=15.0,
    wind_speed_mps=2.0,
    wind_direction=180.0,
    humidity_percent=50.0,
    conditions="Test Feed",
)


class FakeWeatherService:
    """Returns a fixed weather reading without any network access."""

    def __init__(self, reading: WeatherReading) -> None:
        self._reading = reading

    async def fetch(self, latitude: float, longitude: float) -> WeatherReading:
        _ = (latitude, longitude)
        return self._reading


class FakeReportService:
    """Returns fixed report text without calling a language model."""

    def __init__(self, text: str = "TEST REPORT") -> None:
        self._text = text

    async def generate(self, **kwargs: Any) -> str:
        _ = kwargs
        return self._text


def _seed_records(filename: str) -> list[dict[str, Any]]:
    raw = json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))
    return list(raw.values())


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield a session factory over a seeded in-memory SQLite database."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for record in _seed_records("aircraft.json"):
            session.add(AircraftRow(**record))
        for record in _seed_records("payloads.json"):
            session.add(PayloadRow(**record))
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def build_graph(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[WeatherReading], CompiledStateGraph]:
    """Return a factory that builds a graph with a given weather reading."""

    def _make(reading: WeatherReading) -> CompiledStateGraph:
        deps = GraphDependencies(
            session_factory=session_factory,
            weather=FakeWeatherService(reading),  # type: ignore[arg-type]
            report=FakeReportService(),  # type: ignore[arg-type]
        )
        return build_mission_graph(deps, InMemorySaver())

    return _make


@pytest.fixture
def graph(
    build_graph: Callable[[WeatherReading], CompiledStateGraph],
) -> CompiledStateGraph:
    """Return a graph using calm test weather."""
    return build_graph(CALM_WEATHER)
