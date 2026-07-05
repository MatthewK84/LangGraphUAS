"""Domain-specific exceptions.

A single, explicit exception hierarchy keeps error handling consistent across
the codebase (Principle 9). Callers catch the narrowest type they can handle.
"""


class SuasError(Exception):
    """Base class for all application errors."""


class AircraftNotFoundError(SuasError):
    """Raised when a requested aircraft id does not exist."""

    def __init__(self, aircraft_id: str) -> None:
        self.aircraft_id = aircraft_id
        super().__init__(f"Aircraft not found: {aircraft_id}")


class WeatherServiceError(SuasError):
    """Raised when the weather provider cannot be reached after retries."""


class ReportGenerationError(SuasError):
    """Raised when the language model fails to produce a report."""


class SeedDataError(SuasError):
    """Raised when reference seed data cannot be loaded."""
