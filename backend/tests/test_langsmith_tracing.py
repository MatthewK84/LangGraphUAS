"""LangSmith tracing: opt-in, redacted outside a local machine, never in CI (#109).

The redaction tests use the real ``langsmith.Client`` over a fake HTTP session,
so they check the bytes that would leave the process. Nothing here reaches the
service: the session records requests instead of sending them.
"""

import inspect
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from langchain_core.runnables import RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client
from pydantic import ValidationError

from suas import main
from suas.config import Settings, get_settings
from suas.main import lifespan
from suas.tracing import (
    REDACTED,
    UnredactedTracingError,
    build_tracing,
    redact,
    refuse_unredacted_tracing,
    trace_graph,
)

LATITUDE = "34.1234"
LONGITUDE = "-80.5678"
BRIEF = "Launch from the north field"


class _Response:
    status_code = 200
    text = "{}"

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return {}

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        return None


class _RecordingSession:
    """Stands in for ``requests.Session``: records what would be sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        body = kwargs.get("data") or kwargs.get("json") or b""
        self.sent.append(body.decode() if isinstance(body, bytes) else str(body))
        return _Response()

    def mount(self, *_: Any, **__: Any) -> None:
        return None

    def close(self) -> None:
        return None


def _offline(**kwargs: Any) -> Client:
    return Client(session=_RecordingSession(), info={}, **kwargs)  # type: ignore[arg-type]


def _on(**overrides: Any) -> Settings:
    return Settings(langsmith_tracing=True, langsmith_api_key="test-only-key", **overrides)


def _trace_one_mission(settings: Settings) -> str:
    """Run a mission-shaped step through the tracer; return everything sent."""
    session = _RecordingSession()

    def client(**kwargs: Any) -> Client:
        return Client(session=session, auto_batch_tracing=False, info={}, **kwargs)  # type: ignore[arg-type]

    tracing = build_tracing(settings, client_factory=client)
    step = RunnableLambda(lambda state: {"report": f"{BRIEF} at {LATITUDE},{LONGITUDE}"})
    step.invoke(
        {"mission_params": {"latitude": float(LATITUDE), "longitude": float(LONGITUDE)}},
        config={"callbacks": list(tracing.callbacks)},
    )
    tracing.flush()
    return "\n".join(session.sent)


def test_tracing_is_off_by_default() -> None:
    def no_client(**_: Any) -> Client:
        raise AssertionError("tracing is off; no client may be built")

    tracing = build_tracing(Settings(), client_factory=no_client)

    assert tracing.callbacks == ()
    tracing.flush()


def test_tracing_on_without_a_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="SUAS_LANGSMITH_API_KEY"):
        Settings(langsmith_tracing=True)


def test_suas_settings_map_to_the_langsmith_client() -> None:
    seen: dict[str, Any] = {}

    def client(**kwargs: Any) -> Client:
        seen.update(kwargs)
        return Client(session=_RecordingSession(), info={}, **kwargs)  # type: ignore[arg-type]

    tracing = build_tracing(
        _on(langsmith_endpoint="http://127.0.0.1:9", langsmith_project="ops"),
        client_factory=client,
    )

    assert seen["api_key"] == "test-only-key"
    assert seen["api_url"] == "http://127.0.0.1:9"
    assert seen["hide_inputs"] is redact
    assert seen["hide_outputs"] is redact
    assert getattr(tracing.callbacks[0], "project_name", None) == "ops"


def test_coordinates_and_brief_never_leave_the_process_by_default() -> None:
    sent = _trace_one_mission(_on(langsmith_endpoint="http://127.0.0.1:9"))

    assert sent, "the tracer sent nothing, so this test proves nothing"
    assert LATITUDE not in sent
    assert LONGITUDE.lstrip("-") not in sent
    assert BRIEF not in sent


def test_a_local_machine_can_opt_out_of_redaction() -> None:
    sent = _trace_one_mission(_on(langsmith_endpoint="http://127.0.0.1:9", langsmith_redact=False))

    assert LATITUDE in sent
    assert BRIEF in sent


def test_redaction_keeps_numbers_and_hides_coordinates_and_text() -> None:
    run = {
        "mission_params": {"latitude": 34.1, "longitude": -80.2, "distance_m": 2000.0},
        "messages": [{"content": "brief", "type": "human"}],
        "is_viable": True,
        "blockers": None,
    }

    assert redact(run) == {
        "mission_params": {"latitude": REDACTED, "longitude": REDACTED, "distance_m": 2000.0},
        "messages": [{"content": REDACTED, "type": REDACTED}],
        "is_viable": True,
        "blockers": None,
    }


def test_redaction_hides_objects_it_cannot_inspect() -> None:
    assert redact({"reading": object()}) == {"reading": REDACTED}


def test_shutdown_flushes_the_client() -> None:
    flushed: list[bool] = []

    class _Client(Client):
        def flush(self) -> None:
            flushed.append(True)

    def client(**kwargs: Any) -> Client:
        return _Client(session=_RecordingSession(), info={}, **kwargs)  # type: ignore[arg-type]

    build_tracing(_on(langsmith_endpoint="http://127.0.0.1:9"), client_factory=client).flush()

    assert flushed == [True]


def test_the_default_factory_is_langsmiths_client() -> None:
    default = inspect.signature(build_tracing).parameters["client_factory"].default

    assert default is Client


@pytest.mark.parametrize("name", ["LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"])
def test_langchains_own_unredacted_tracing_switch_is_refused(name: str) -> None:
    with pytest.raises(UnredactedTracingError, match="SUAS_LANGSMITH_TRACING"):
        refuse_unredacted_tracing({name: "true"})


def test_the_switch_set_false_or_absent_is_fine() -> None:
    refuse_unredacted_tracing({"LANGSMITH_TRACING": "false"})
    refuse_unredacted_tracing({})


def test_the_graph_carries_the_tracer_only_when_tracing_is_on() -> None:
    graph = RunnableLambda(lambda state: state)
    off = build_tracing(Settings())

    assert trace_graph(graph, off) is graph

    on = build_tracing(_on(langsmith_endpoint="http://127.0.0.1:9"), client_factory=_offline)
    traced = trace_graph(graph, on)

    assert list(traced.config["callbacks"]) == list(on.callbacks)  # type: ignore[attr-defined]


# --- the lifespan -------------------------------------------------------------


def _settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUAS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'trace.db'}")
    monkeypatch.setenv("SUAS_API_KEY", "")
    get_settings.cache_clear()


async def test_startup_refuses_langchains_unredacted_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    try:
        with pytest.raises(UnredactedTracingError):
            async with lifespan(FastAPI()):
                pass
    finally:
        get_settings.cache_clear()


async def test_the_app_traces_both_graphs_and_flushes_on_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flushed: list[bool] = []

    class _Client(Client):
        def flush(self) -> None:
            flushed.append(True)

    def client(**kwargs: Any) -> Client:
        return _Client(session=_RecordingSession(), info={}, **kwargs)  # type: ignore[arg-type]

    _settings_env(monkeypatch, tmp_path)
    monkeypatch.setenv("SUAS_LANGSMITH_TRACING", "true")
    monkeypatch.setenv("SUAS_LANGSMITH_API_KEY", "test-only-key")
    monkeypatch.setenv("SUAS_LANGSMITH_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setattr(
        main, "build_tracing", lambda settings: build_tracing(settings, client_factory=client)
    )
    app = FastAPI()
    try:
        async with lifespan(app):
            for graph in (app.state.graph, app.state.replan_graph):
                assert [type(c) for c in graph.config["callbacks"]] == [LangChainTracer]
            assert flushed == []
    finally:
        get_settings.cache_clear()

    assert flushed == [True]
