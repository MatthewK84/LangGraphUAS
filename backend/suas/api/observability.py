"""Observability: request correlation, access logging, and metrics.

Every response carries an ``X-Request-ID`` header. The same id is bound to a
context variable so all log records emitted while handling the request include
it, which makes traces greppable end to end.

Metrics are exposed in Prometheus text format from a small in-process registry.
No external metrics dependency is required.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from threading import Lock
from typing import Final
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from suas.logging_config import request_id_var

logger: Final[logging.Logger] = logging.getLogger(__name__)

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"

CallNext = Callable[[Request], Awaitable[Response]]


def _route_template(request: Request) -> str:
    """Return the matched route template, falling back to the raw path.

    Using the template (for example ``/api/plan/{thread_id}``) keeps metric
    label cardinality bounded instead of creating a series per unique path.
    """
    route: object = request.scope.get("route")
    path: object = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return request.url.path


class MetricsRegistry:
    """Thread-safe counters and latency sums for Prometheus exposition."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = {}
        self._latency_sum_s: dict[tuple[str, str], float] = {}
        self._plan_outcomes: dict[str, int] = {"go": 0, "no_go": 0}
        self._weather_source: dict[str, int] = {"live": 0, "fallback": 0}

    def record_request(self, method: str, path: str, code: int, duration_s: float) -> None:
        """Record one completed HTTP request."""
        with self._lock:
            key = (method, path, code)
            self._requests[key] = self._requests.get(key, 0) + 1
            lat_key = (method, path)
            self._latency_sum_s[lat_key] = self._latency_sum_s.get(lat_key, 0.0) + duration_s

    def record_plan(self, *, is_viable: bool, weather_live: bool) -> None:
        """Record the outcome of one mission plan."""
        with self._lock:
            self._plan_outcomes["go" if is_viable else "no_go"] += 1
            self._weather_source["live" if weather_live else "fallback"] += 1

    def render(self) -> str:
        """Return the current metrics in Prometheus text exposition format."""
        with self._lock:
            lines: list[str] = [
                "# HELP suas_http_requests_total Total HTTP requests.",
                "# TYPE suas_http_requests_total counter",
            ]
            for (method, path, code), count in sorted(self._requests.items()):
                lines.append(
                    f'suas_http_requests_total{{method="{method}",path="{path}",'
                    f'code="{code}"}} {count}'
                )
            lines += [
                "# HELP suas_http_request_duration_seconds_sum Summed request latency.",
                "# TYPE suas_http_request_duration_seconds_sum counter",
            ]
            for (method, path), total in sorted(self._latency_sum_s.items()):
                lines.append(
                    f'suas_http_request_duration_seconds_sum{{method="{method}",'
                    f'path="{path}"}} {total:.6f}'
                )
            lines += [
                "# HELP suas_plan_outcomes_total Mission plan go/no-go outcomes.",
                "# TYPE suas_plan_outcomes_total counter",
            ]
            for outcome, count in sorted(self._plan_outcomes.items()):
                lines.append(f'suas_plan_outcomes_total{{outcome="{outcome}"}} {count}')
            lines += [
                "# HELP suas_weather_source_total Weather readings by provenance.",
                "# TYPE suas_weather_source_total counter",
            ]
            for source, count in sorted(self._weather_source.items()):
                lines.append(f'suas_weather_source_total{{source="{source}"}} {count}')
            return "\n".join(lines) + "\n"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, logs access, and records request metrics."""

    def __init__(self, app: ASGIApp, metrics: MetricsRegistry) -> None:
        super().__init__(app)
        self._metrics = metrics

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        """Wrap the request with correlation, timing, and metrics."""
        incoming: str | None = request.headers.get(REQUEST_ID_HEADER)
        request_id: str = incoming if incoming else str(uuid4())
        token = request_id_var.set(request_id)
        started: float = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_s: float = time.perf_counter() - started
        self._metrics.record_request(
            request.method,
            _route_template(request),
            response.status_code,
            duration_s,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "%s %s -> %d in %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_s * 1000.0,
        )
        return response
