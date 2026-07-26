"""Centralized logging configuration.

Supports plain and JSON output. JSON is the production default so logs are
machine-parseable, and every record carries the current request id when one is
in scope.

Implementation note: level resolution uses ``logging.getLevelName`` rather than
``logging.getLevelNamesMapping`` because the latter is only available on Python
3.11 and later. This module supports 3.10 through 3.12.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any, Final

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)

# Correlation id for the in-flight request. Defaults to "-" outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def resolve_level(level: str) -> int:
    """Return the numeric logging level for a level name.

    Falls back to ``INFO`` when the name is not recognized. Portable across
    Python 3.10 to 3.12.

    Args:
        level: A level name such as ``INFO`` or ``debug``.
    """
    name: str = level.strip().upper()
    if name not in _VALID_LEVELS:
        return logging.INFO
    resolved: int | str = logging.getLevelName(name)
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


class RequestIdFilter(logging.Filter):
    """Attaches the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` and always allow the record through."""
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Renders log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a compact JSON string."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str, *, json_output: bool = True) -> None:
    """Configure root logging once at startup.

    Args:
        level: A logging level name such as ``INFO`` or ``DEBUG``.
        json_output: Emit JSON when true, human-readable text otherwise.
    """
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolve_level(level))
