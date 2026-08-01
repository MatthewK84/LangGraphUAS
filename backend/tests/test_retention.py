"""Tests for checkpoint retention.

Retention exists because LangGraph never expires checkpoints: without it the
checkpoint tables grow for the life of the deployment.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.models import MissionThreadRow
from suas.db.retention import purge_expired_threads, record_thread


class _RecordingSaver(InMemorySaver):
    """In-memory saver that records which threads were asked to be deleted."""

    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        await super().adelete_thread(thread_id)


class _FailingSaver(InMemorySaver):
    """Saver whose deletes always fail, to exercise the retry path."""

    async def adelete_thread(self, thread_id: str) -> None:
        raise RuntimeError("checkpoint backend unavailable")


async def _age_thread(
    session_factory: async_sessionmaker[AsyncSession], thread_id: str, days: float
) -> None:
    """Backdate a recorded thread so it falls outside the retention window."""
    async with session_factory() as session:
        row = await session.get(MissionThreadRow, thread_id)
        assert row is not None
        row.created_at = datetime.now(timezone.utc) - timedelta(days=days)
        await session.commit()


async def test_record_thread_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await record_thread(session, "thread-a")
    async with session_factory() as session:
        first = await session.get(MissionThreadRow, "thread-a")
        assert first is not None
        original = first.created_at
    async with session_factory() as session:
        await record_thread(session, "thread-a")
    async with session_factory() as session:
        again = await session.get(MissionThreadRow, "thread-a")
    assert again is not None
    assert again.created_at == original


async def test_purge_removes_only_threads_past_the_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    saver = _RecordingSaver()
    async with session_factory() as session:
        await record_thread(session, "old-thread")
        await record_thread(session, "fresh-thread")
    await _age_thread(session_factory, "old-thread", days=45.0)

    purged = await purge_expired_threads(session_factory, saver, retention_days=30.0)

    assert purged == 1
    assert saver.deleted == ["old-thread"]
    async with session_factory() as session:
        assert await session.get(MissionThreadRow, "old-thread") is None
        assert await session.get(MissionThreadRow, "fresh-thread") is not None


async def test_purge_is_disabled_when_retention_is_zero(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    saver = _RecordingSaver()
    async with session_factory() as session:
        await record_thread(session, "ancient")
    await _age_thread(session_factory, "ancient", days=9999.0)

    purged = await purge_expired_threads(session_factory, saver, retention_days=0.0)

    assert purged == 0
    assert saver.deleted == []
    async with session_factory() as session:
        assert await session.get(MissionThreadRow, "ancient") is not None


async def test_purge_keeps_tracking_row_when_delete_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A failed checkpoint delete must be retried, not silently orphaned."""
    async with session_factory() as session:
        await record_thread(session, "stubborn")
    await _age_thread(session_factory, "stubborn", days=45.0)

    purged = await purge_expired_threads(session_factory, _FailingSaver(), retention_days=30.0)

    assert purged == 0
    async with session_factory() as session:
        assert await session.get(MissionThreadRow, "stubborn") is not None


async def test_purge_with_nothing_expired_is_a_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    saver = _RecordingSaver()
    async with session_factory() as session:
        await record_thread(session, "recent")

    purged = await purge_expired_threads(session_factory, saver, retention_days=30.0)

    assert purged == 0
    assert saver.deleted == []


async def test_planning_records_a_thread_for_retention(
    app_with_graph: Any, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The plan endpoint must register its thread so retention can find it."""
    transport = httpx.ASGITransport(app=app_with_graph)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/plan",
            json={
                "aircraft_id": "Skydio_X10D",
                "payload_id": "None",
                "mission_params": {
                    "distance_m": 1000.0,
                    "hover_time_s": 60.0,
                    "target_altitude_m": 120.0,
                    "elevation_m": 0.0,
                    "latitude": 34.0,
                    "longitude": -80.0,
                },
            },
        )
    assert response.status_code == 200
    thread_id = response.json()["thread_id"]
    async with session_factory() as session:
        assert await session.get(MissionThreadRow, thread_id) is not None
