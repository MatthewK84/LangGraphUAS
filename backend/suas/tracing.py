"""LangSmith tracing: off by default, redacted unless a local machine opts out (#109).

Tracing is the easiest way to send mission coordinates and raw briefs to a
third party by accident, so it is built to fail closed:

* Off unless ``SUAS_LANGSMITH_TRACING=true``, which needs ``SUAS_LANGSMITH_API_KEY``.
* The ``SUAS_LANGSMITH_*`` settings go to one ``langsmith.Client`` built here,
  the same values ``LANGSMITH_API_KEY``, ``LANGSMITH_ENDPOINT`` and
  ``LANGSMITH_PROJECT`` would set. LangChain's own ``LANGSMITH_TRACING`` switch
  is refused at startup: it attaches a default client that redacts nothing.
* Run inputs and outputs pass through :func:`redact` before they are sent,
  unless ``SUAS_LANGSMITH_REDACT=false``, which is for a local machine only.
* The lifespan flushes the client on shutdown so queued runs are not lost.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import Runnable
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client

from suas.config import Settings

REDACTED: Final[str] = "[redacted]"
COORDINATE_KEYS: Final[frozenset[str]] = frozenset({"latitude", "longitude"})
UNREDACTED_SWITCHES: Final[tuple[str, ...]] = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")

ClientFactory = Callable[..., Client]
G = TypeVar("G", bound=Runnable[Any, Any])


class UnredactedTracingError(RuntimeError):
    """LangChain's own tracing switch is on, which would bypass redaction."""


def redact(value: Any) -> Any:
    """Hide coordinates and every piece of text; keep numbers, flags and shape.

    Briefs, prompts and messages are free text that can quote a position, so
    all strings go. Anything that is not plain data is hidden rather than
    trusted to serialise harmlessly.
    """
    if isinstance(value, Mapping):
        return {
            key: REDACTED if key in COORDINATE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return REDACTED


@dataclass(frozen=True)
class Tracing:
    """The callbacks every graph run carries, and the client behind them."""

    callbacks: tuple[BaseCallbackHandler, ...] = ()
    client: Client | None = None

    def flush(self) -> None:
        """Send queued runs before the process exits."""
        if self.client is not None:
            self.client.flush()


def build_tracing(settings: Settings, *, client_factory: ClientFactory = Client) -> Tracing:
    """Return no tracer unless tracing is opted in; otherwise a redacting one."""
    if not settings.langsmith_tracing:
        return Tracing()
    hide = redact if settings.langsmith_redact else None
    client = client_factory(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
        hide_inputs=hide,
        hide_outputs=hide,
    )
    tracer = LangChainTracer(client=client, project_name=settings.langsmith_project)
    return Tracing(callbacks=(tracer,), client=client)


def refuse_unredacted_tracing(environ: Mapping[str, str]) -> None:
    """Fail startup if LangChain's own, unredacted, tracing switch is on."""
    on: Sequence[str] = [
        name for name in UNREDACTED_SWITCHES if environ.get(name, "").lower() == "true"
    ]
    if on:
        raise UnredactedTracingError(
            f"{', '.join(on)} traces every run unredacted; unset it and use "
            "SUAS_LANGSMITH_TRACING=true, which redacts coordinates and briefs"
        )


def trace_graph(graph: G, tracing: Tracing) -> G:
    """Return the graph with the tracer on every run, or unchanged when off."""
    if not tracing.callbacks:
        return graph
    traced: G = graph.with_config(callbacks=list(tracing.callbacks))  # type: ignore[assignment]
    return traced
