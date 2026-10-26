"""Centralized logging configuration.

Supports plain and JSON output. JSON is the production default so logs are
machine-parseable, and every record carries the current request id when one is
in scope, plus the trace fields that tie a plan's lines to the calculator, the
weather and the granted mode that produced them ("-" until each is known).

Implementation note: level resolution uses ``logging.getLevelName`` rather than
``logging.getLevelNamesMapping`` because the latter is only available on Python
3.11 and later. This module supports 3.10 through 3.12.
"""

import json
import logging
from contextvars import ContextVar, Token
from typing import Any, Final

TRACE_FIELDS: Final[tuple[str, ...]] = ("calculator_version", "weather_source", "assessment_mode")
_LOG_FORMAT: Final[str] = (
    "%(asctime)s %(levelname)s %(name)s [%(request_id)s] "
    + " ".join(f"{name}=%({name})s" for name in TRACE_FIELDS)
    + " %(message)s"
)
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)

# Correlation id for the in-flight request. Defaults to "-" outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Trace fields for the in-flight request. A mutable dict rather than one
# ContextVar per field: graph nodes run in copied contexts, so a value they set
# would never reach the route's later lines, but a change to a shared dict does.
trace_var: ContextVar[dict[str, str] | None] = ContextVar("trace", default=None)


def start_trace(**fields: str) -> Token[dict[str, str] | None]:
    """Open a fresh set of trace fields for one request; return its reset token."""
    return trace_var.set(dict.fromkeys(TRACE_FIELDS, "-") | fields)


def annotate_trace(**fields: str) -> None:
    """Record trace fields as they become known; a no-op outside a request."""
    current = trace_var.get()
    if current is not None:
        current.update(fields)


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
    """Attaches the current request id and trace fields to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` and the trace fields; always allow the record."""
        record.request_id = request_id_var.get()
        trace = trace_var.get() or {}
        for name in TRACE_FIELDS:
            setattr(record, name, trace.get(name, "-"))
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
        for name in TRACE_FIELDS:
            payload[name] = getattr(record, name, "-")
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def text_formatter() -> logging.Formatter:
    """Return the human-readable formatter; it needs ``RequestIdFilter`` upstream."""
    return logging.Formatter(_LOG_FORMAT)


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
        handler.setFormatter(text_formatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolve_level(level))
