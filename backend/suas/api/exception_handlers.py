"""Global exception handlers.

Maps the domain exception hierarchy onto HTTP responses in one place so routes
stay free of repetitive try/except blocks and every error shares a response
shape (Principle 9).
"""

import logging
from typing import Final

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from suas.errors import (
    AircraftNotFoundError,
    ReportGenerationError,
    SeedDataError,
    SuasError,
    WeatherServiceError,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)

_STATUS_MAP: Final[dict[type[SuasError], int]] = {
    AircraftNotFoundError: status.HTTP_404_NOT_FOUND,
    WeatherServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    ReportGenerationError: status.HTTP_502_BAD_GATEWAY,
    SeedDataError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _error_body(detail: str, error_type: str) -> dict[str, str]:
    """Return the standard error response body."""
    return {"detail": detail, "error": error_type}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach domain and catch-all exception handlers to the application."""

    @app.exception_handler(SuasError)
    async def handle_suas_error(request: Request, exc: SuasError) -> JSONResponse:
        """Translate a known domain error into its mapped status code."""
        _ = request
        code: int = _STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        logger.warning("Domain error %s: %s", type(exc).__name__, exc)
        return JSONResponse(
            status_code=code,
            content=_error_body(str(exc), type(exc).__name__),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Return a generic 500 without leaking internal detail to the client."""
        _ = request
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("Internal server error", "InternalError"),
        )
