"""Graph dependency container.

Nodes receive their collaborators through this frozen container rather than
reaching for module-level globals (Principle 2). This makes every node testable
with fakes.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.calculations.battery import DEFAULT_RESERVE_PERCENT
from suas.services.llm import ReportService
from suas.services.weather import WeatherService


@dataclass(frozen=True)
class GraphDependencies:
    """Collaborators required by the mission graph nodes."""

    session_factory: async_sessionmaker[AsyncSession]
    weather: WeatherService
    report: ReportService
    battery_reserve_percent: float = DEFAULT_RESERVE_PERCENT
