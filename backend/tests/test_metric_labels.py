"""Every metric and label the docs name is one /metrics emits (#112).

An operator following the docs builds a dashboard against what they name, so
a documented label with no emitter is a dashboard of empty panels. These tests
read every backticked metric in the docs that describe /metrics and compare it,
label by label, with the exporter as rendered after one event of each kind.
They also pin the labels the issue asks for: the granted mode on plan outcomes,
the real weather source (not live-or-fallback), the reason a brief was
suppressed, and contention on the per-thread ack lock.
"""

import asyncio
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from suas.api import thread_locks
from suas.api.observability import MetricsRegistry
from suas.api.thread_locks import thread_lock
from suas.schemas.responses import WeatherSource
from tests.test_ack import _BODY

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = (
    "docs/engineering-practices.md",
    "docs/ops.md",
    "docs/injection-defense.md",
    "README.md",
)
_REFERENCE = re.compile(r"`(suas_[a-z_]+)(?:\{([^}`]*)\})?`")
_UNPREFIXED = re.compile(
    r"`(?:injection_quarantine|llm_field_violations|hallucinated_citation|brief_suppressed|unverified_span)_total"
)


def _rendered() -> str:
    metrics = MetricsRegistry()
    metrics.record_request("POST", "/api/plan", 401, 0.01)
    metrics.record_plan(is_viable=True, mode="advisory", weather_source="cached_stale")
    metrics.record_seal_violations(1)
    metrics.record_brief_suppressed("contradiction")
    metrics.record_hallucinated_citations(1)
    metrics.set_quarantine_open(1)
    metrics.set_lock_contention("thread", 1)
    return metrics.render()


def _labels(rendered: str, name: str) -> set[str]:
    found: set[str] = set()
    for labels in re.findall(rf"^{name}\{{([^}}]*)\}}", rendered, re.MULTILINE):
        found |= {pair.split("=", 1)[0] for pair in labels.split(",")}
    return found


def _references() -> list[tuple[str, str, set[str]]]:
    refs = []
    for doc in _DOCS:
        for name, labels in _REFERENCE.findall((_ROOT / doc).read_text()):
            keys = {part.split("=", 1)[0].strip() for part in labels.split(",") if part.strip()}
            refs.append((doc, name, keys))
    return refs


def test_the_docs_name_metrics_at_all() -> None:
    names = {name for _, name, _ in _references()}
    assert {
        "suas_plan_outcomes_total",
        "suas_weather_source_total",
        "suas_lock_contention_total",
    } <= names


@pytest.mark.parametrize(("doc", "name", "labels"), _references())
def test_every_documented_metric_and_label_is_emitted(
    doc: str, name: str, labels: set[str]
) -> None:
    rendered = _rendered()
    assert f"# TYPE {name} " in rendered, f"{doc} names {name}, which /metrics never emits"
    missing = labels - _labels(rendered, name)
    assert not missing, (
        f"{doc} names {name}{{{','.join(sorted(missing))}}}; /metrics has no such label"
    )


@pytest.mark.parametrize("doc", _DOCS)
def test_no_doc_names_the_old_unprefixed_counters(doc: str) -> None:
    assert not _UNPREFIXED.search((_ROOT / doc).read_text()), doc


def test_the_practices_doc_names_the_four_labels() -> None:
    practices = (_ROOT / "docs/engineering-practices.md").read_text()
    for reference in (
        "`suas_plan_outcomes_total{outcome,mode}`",
        "`suas_weather_source_total{source}`",
        "`suas_brief_suppressed_total{reason}`",
        "`suas_lock_contention_total{lock}`",
    ):
        assert reference in practices, reference


# --- the labels themselves ----------------------------------------------------


def test_plan_outcomes_carry_the_granted_mode() -> None:
    metrics = MetricsRegistry()
    metrics.record_plan(is_viable=False, mode="operational", weather_source="live")
    rendered = metrics.render()
    assert 'suas_plan_outcomes_total{outcome="no_go",mode="operational"} 1' in rendered
    assert 'suas_plan_outcomes_total{outcome="go",mode="advisory"} 0' in rendered


def test_weather_source_counts_the_real_provenance() -> None:
    # The bug: a cached reading was counted as "fallback", a fresh one too.
    metrics = MetricsRegistry()
    metrics.record_plan(is_viable=True, mode="advisory", weather_source="cached_fresh")
    metrics.record_plan(is_viable=True, mode="advisory", weather_source="cached_stale")
    rendered = metrics.render()
    for source in WeatherSource:
        expected = 1 if source in (WeatherSource.CACHED_FRESH, WeatherSource.CACHED_STALE) else 0
        assert f'suas_weather_source_total{{source="{source.value}"}} {expected}' in rendered


def test_a_plan_with_no_reading_counts_as_none() -> None:
    metrics = MetricsRegistry()
    metrics.record_plan(is_viable=False, mode="advisory", weather_source="none")
    assert 'suas_weather_source_total{source="none"} 1' in metrics.render()


async def test_lock_contention_counts_only_waits() -> None:
    before = thread_locks.contended_waits()
    async with thread_lock("solo"):
        pass
    assert thread_locks.contended_waits() == before

    held = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with thread_lock("busy"):
            held.set()
            await release.wait()

    async def waiter() -> None:
        async with thread_lock("busy"):
            pass

    holding = asyncio.create_task(holder())
    await held.wait()
    waiting = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(holding, waiting)
    assert thread_locks.contended_waits() == before + 1


async def test_metrics_endpoint_shows_a_plans_mode_source_and_lock_series(
    app_with_graph: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=app_with_graph)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/plan", json=_BODY)).status_code == 200
        text = (await client.get("/metrics")).text
    assert re.search(
        r'^suas_plan_outcomes_total\{outcome="(go|no_go)",mode="advisory"\} 1$', text, re.M
    )
    assert re.search(r'^suas_weather_source_total\{source="live"\} 1$', text, re.M)
    assert re.search(r'^suas_lock_contention_total\{lock="thread"\} \d+$', text, re.M)
