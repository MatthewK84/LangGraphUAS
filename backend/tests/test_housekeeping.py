"""Retention runs on a schedule, not only at startup (#86).

Before this, checkpoint retention ran once when a process started, so a
long-lived worker never purged and ``SUAS_CHECKPOINT_RETENTION_DAYS`` meant
nothing in production. Housekeeping now repeats every
``SUAS_RETENTION_INTERVAL_S`` in every worker, so each pass must be safe to run
twice at once: a thread is claimed by deleting its tracking row, and an idle
rate-limit bucket is re-checked under a skip-locked row lock.

Set SUAS_TEST_POSTGRES_URL to run the two-worker cases on Postgres, as the
postgres-integration CI job does.
"""

import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from suas.api.ratelimit import DatabaseLimiter, prune_idle_buckets
from suas.config import Settings, get_settings
from suas.db.engine import create_engine, create_schema, create_session_factory
from suas.db.models import MissionThreadRow, RateLimitBucketRow
from suas.db.retention import next_replan_thread_id, purge_expired_threads, record_thread
from suas.main import lifespan
from tests.test_shared_rate_limit import postgres_url

__all__ = ["postgres_url"]  # a fixture, used by name

_ROOT = Path(__file__).resolve().parents[2]
_NOW = 1_000_000.0
_WINDOW_S = 60.0


class _State(TypedDict):
    n: int


class _CountingSaver(InMemorySaver):
    """An in-memory saver that counts how often each thread is deleted."""

    def __init__(self, fail_on: str = "", delay_s: float = 0.0) -> None:
        super().__init__()
        self.deletes: dict[str, int] = {}
        self._fail_on = fail_on
        self._delay_s = delay_s  # a slow backend widens the window two passes share

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.sleep(self._delay_s)
        if thread_id == self._fail_on:
            raise RuntimeError("checkpoint backend unavailable")
        self.deletes[thread_id] = self.deletes.get(thread_id, 0) + 1
        await super().adelete_thread(thread_id)


async def _checkpoint(saver: InMemorySaver, *thread_ids: str) -> None:
    builder = StateGraph(_State)
    builder.add_node("step", lambda state: {"n": state["n"] + 1})
    builder.add_edge(START, "step")
    builder.add_edge("step", END)
    graph = builder.compile(checkpointer=saver)
    for thread_id in thread_ids:
        await graph.ainvoke({"n": 0}, {"configurable": {"thread_id": thread_id}})


async def _has_checkpoint(saver: InMemorySaver, thread_id: str) -> bool:
    config: Any = {"configurable": {"thread_id": thread_id}}
    return await saver.aget_tuple(config) is not None


async def _thread(
    factory: async_sessionmaker[AsyncSession], thread_id: str, *, days_old: float, replans: int = 0
) -> None:
    async with factory() as session:
        await record_thread(session, thread_id)
    for _ in range(replans):
        async with factory() as session:
            await next_replan_thread_id(session, thread_id)
    async with factory() as session:
        row = await session.get(MissionThreadRow, thread_id)
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(days=days_old)
        await session.commit()


async def _threads_left(factory: async_sessionmaker[AsyncSession]) -> set[str]:
    async with factory() as session:
        return set((await session.execute(select(MissionThreadRow.thread_id))).scalars())


# --- replan children ----------------------------------------------------------


async def test_purging_a_thread_purges_its_replan_children_and_nothing_else(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    saver = _CountingSaver()
    await _thread(session_factory, "old", days_old=45.0, replans=2)
    await _thread(session_factory, "keep", days_old=1.0, replans=1)
    await _checkpoint(saver, "old", "old:1", "old:2", "keep", "keep:1")

    assert await purge_expired_threads(session_factory, saver, retention_days=30.0) == 1

    for gone in ("old", "old:1", "old:2"):
        assert not await _has_checkpoint(saver, gone), gone
    for kept in ("keep", "keep:1"):
        assert await _has_checkpoint(saver, kept), kept
    assert await _threads_left(session_factory) == {"keep"}


async def test_a_failed_child_delete_keeps_the_thread_for_the_next_pass(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _thread(session_factory, "old", days_old=45.0, replans=2)

    failing = _CountingSaver(fail_on="old:2")
    assert await purge_expired_threads(session_factory, failing, retention_days=30.0) == 0
    assert await _threads_left(session_factory) == {"old"}

    working = _CountingSaver()
    assert await purge_expired_threads(session_factory, working, retention_days=30.0) == 1
    assert working.deletes == {"old": 1, "old:1": 1, "old:2": 1}


# --- two workers purging at once ----------------------------------------------


async def _two_workers(
    url: str,
) -> tuple[list[async_sessionmaker[AsyncSession]], list[AsyncEngine]]:
    engines = [create_engine(url) for _ in range(2)]
    await create_schema(engines[0])
    return [create_session_factory(engine) for engine in engines], engines


async def _assert_each_thread_purged_once(url: str) -> None:
    factories, engines = await _two_workers(url)
    try:
        names = [f"t{i}" for i in range(12)]
        for name in names:
            await _thread(factories[0], name, days_old=45.0, replans=1)
        saver = _CountingSaver(delay_s=0.01)

        counts = await asyncio.gather(
            *(purge_expired_threads(factory, saver, retention_days=30.0) for factory in factories)
        )

        assert sum(counts) == len(names)
        assert saver.deletes == dict.fromkeys(names + [f"{name}:1" for name in names], 1)
        assert await _threads_left(factories[1]) == set()
    finally:
        for engine in engines:
            await engine.dispose()


async def test_two_workers_purge_each_thread_once_on_sqlite(tmp_path: Path) -> None:
    await _assert_each_thread_purged_once(f"sqlite+aiosqlite:///{tmp_path / 'h.db'}")


async def test_two_workers_purge_each_thread_once_on_postgres(postgres_url: str) -> None:
    await _assert_each_thread_purged_once(postgres_url)


# --- idle rate-limit buckets --------------------------------------------------


async def _buckets(factory: async_sessionmaker[AsyncSession], **rows: list[float]) -> None:
    async with factory() as session:
        session.add_all(RateLimitBucketRow(bucket=name, hits=hits) for name, hits in rows.items())
        await session.commit()


async def _buckets_left(factory: async_sessionmaker[AsyncSession]) -> dict[str, list[float]]:
    async with factory() as session:
        rows = (await session.execute(select(RateLimitBucketRow))).scalars()
        return {row.bucket: row.hits for row in rows}


async def test_only_idle_buckets_are_pruned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _buckets(
        session_factory,
        idle=[_NOW - 600.0, _NOW - 120.0],
        empty=[],
        edge=[_NOW - _WINDOW_S],  # exactly one window old: already out of it
        live=[_NOW - 120.0, _NOW - 5.0],
    )

    pruned = await prune_idle_buckets(session_factory, _WINDOW_S, clock=lambda: _NOW)

    assert pruned == 3
    assert await _buckets_left(session_factory) == {"live": [_NOW - 120.0, _NOW - 5.0]}


async def test_a_bucket_mid_admission_is_skipped_not_waited_on(postgres_url: str) -> None:
    factories, engines = await _two_workers(postgres_url)
    try:
        await _buckets(factories[0], busy=[_NOW - 600.0], idle=[_NOW - 600.0])
        async with factories[0]() as admitting, admitting.begin():
            locked = select(RateLimitBucketRow).where(RateLimitBucketRow.bucket == "busy")
            row = (await admitting.execute(locked.with_for_update())).scalar_one()
            pruned = await asyncio.wait_for(
                prune_idle_buckets(factories[1], _WINDOW_S, clock=lambda: _NOW), timeout=5.0
            )
            row.hits = [_NOW]
        assert pruned == 1
        assert await _buckets_left(factories[1]) == {"busy": [_NOW]}
    finally:
        for engine in engines:
            await engine.dispose()


async def test_an_admission_survives_its_idle_row_being_pruned(postgres_url: str) -> None:
    # The admission's insert-if-missing must lock the row, or a prune that
    # deletes it between that insert and the lock leaves nothing to lock.
    factories, engines = await _two_workers(postgres_url)
    try:
        bucket = hashlib.sha256(b"key:alpha").hexdigest()
        await _buckets(factories[0], **{bucket: [_NOW - 600.0]})
        limiter = DatabaseLimiter(factories[1], 5, _WINDOW_S, clock=lambda: _NOW)
        async with factories[0]() as pruning, pruning.begin():
            locked = select(RateLimitBucketRow).where(RateLimitBucketRow.bucket == bucket)
            row = (await pruning.execute(locked.with_for_update())).scalar_one()
            admission = asyncio.create_task(limiter.admit("key:alpha"))
            await asyncio.sleep(0.3)
            await pruning.delete(row)
        assert await asyncio.wait_for(admission, timeout=5.0) == 0
        assert await _buckets_left(factories[0]) == {bucket: [_NOW]}
    finally:
        for engine in engines:
            await engine.dispose()


# --- the schedule -------------------------------------------------------------


def test_the_interval_defaults_to_an_hour_and_must_be_positive() -> None:
    assert Settings().retention_interval_s == 3600.0
    with pytest.raises(ValidationError):
        Settings(retention_interval_s=0.0)


async def _eventually(check: Any, timeout_s: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if await check():
            return True
        await asyncio.sleep(0.05)
    return False


async def test_a_running_app_purges_without_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import FastAPI

    monkeypatch.setenv("SUAS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'live.db'}")
    monkeypatch.setenv("SUAS_API_KEY", "")
    monkeypatch.setenv("SUAS_RETENTION_INTERVAL_S", "0.1")
    get_settings.cache_clear()
    app = FastAPI()
    try:
        async with lifespan(app):
            factory = app.state.session_factory
            # Both arrive after startup's pass, so only the schedule can remove them.
            await _thread(factory, "old", days_old=45.0)
            await _buckets(factory, idle=[1.0])

            async def gone() -> bool:
                left = await _buckets_left(factory)
                return not left and await _threads_left(factory) == set()

            assert await _eventually(gone)
        assert not [t for t in asyncio.all_tasks() if t.get_name() == "suas-housekeeping"]
    finally:
        get_settings.cache_clear()


# --- docs and CI --------------------------------------------------------------


def _text(relative: str) -> str:
    return re.sub(r"\s+", " ", (_ROOT / relative).read_text())


def test_the_docs_stop_saying_retention_needs_a_restart() -> None:
    readme, ops = _text("README.md"), _text("docs/ops.md")
    for doc in (readme, ops):
        assert "SUAS_RETENTION_INTERVAL_S" in doc
    assert "A process that never restarts never purges" not in ops
    assert "schedule a periodic restart" not in readme


def test_ci_runs_the_two_worker_purge_on_postgres() -> None:
    import yaml

    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["postgres-integration"]["steps"]
    runs = " ".join(str(step.get("run", "")) for step in steps)
    assert "tests/test_housekeeping.py" in runs
