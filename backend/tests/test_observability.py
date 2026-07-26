"""Unit tests for logging, metrics, and rate limiting primitives."""

import logging

from suas.api.observability import MetricsRegistry
from suas.api.ratelimit import SlidingWindowLimiter
from suas.logging_config import JsonFormatter, resolve_level


def test_resolve_level_known_names() -> None:
    assert resolve_level("DEBUG") == logging.DEBUG
    assert resolve_level("warning") == logging.WARNING


def test_resolve_level_unknown_falls_back_to_info() -> None:
    assert resolve_level("not-a-level") == logging.INFO
    assert resolve_level("") == logging.INFO


def test_json_formatter_emits_parseable_json() -> None:
    import json

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"


def test_metrics_registry_counts_requests_and_plans() -> None:
    registry = MetricsRegistry()
    registry.record_request("GET", "/health", 200, 0.01)
    registry.record_request("GET", "/health", 200, 0.02)
    registry.record_plan(is_viable=True, weather_live=False)
    rendered = registry.render()
    assert 'suas_http_requests_total{method="GET",path="/health",code="200"} 2' in rendered
    assert 'suas_plan_outcomes_total{outcome="go"} 1' in rendered
    assert 'suas_weather_source_total{source="fallback"} 1' in rendered


def test_limiter_allows_up_to_limit_then_blocks() -> None:
    limiter = SlidingWindowLimiter(max_requests=3, window_s=60.0)
    assert [limiter.check("client") for _ in range(3)] == [True, True, True]
    assert limiter.check("client") is False


def test_limiter_isolates_clients() -> None:
    limiter = SlidingWindowLimiter(max_requests=1, window_s=60.0)
    assert limiter.check("a") is True
    assert limiter.check("b") is True
    assert limiter.check("a") is False


def test_limiter_window_expiry_allows_again() -> None:
    limiter = SlidingWindowLimiter(max_requests=1, window_s=0.01)
    assert limiter.check("c") is True
    import time

    time.sleep(0.02)
    assert limiter.check("c") is True


def test_retry_after_is_positive_when_blocked() -> None:
    limiter = SlidingWindowLimiter(max_requests=1, window_s=30.0)
    limiter.check("d")
    assert limiter.retry_after_s("d") >= 1
