"""Checkpoint retention.

Every planned mission writes a durable LangGraph checkpoint. Nothing in
LangGraph expires them, so without this the checkpoint tables grow for the life
of the deployment.

The checkpoint tables carry no timestamp we can portably query, so this module
records each thread's creation time in a table the application owns, then ages
threads out through the checkpointer's public ``adelete_thread`` API. Nothing
here depends on LangGraph's internal schema.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.db.models import MissionThreadRow

logger: Final[logging.Logger] = logging.getLogger(__name__)

# Bound the work a single purge will attempt, so a long-neglected deployment
# degrades into several passes instead of one unbounded transaction.
_MAX_THREADS_PER_PURGE: Final[int] = 1000


async def record_thread(
    session: AsyncSession, thread_id: str, operator_key_id: str | None = None
) -> None:
    """Record a thread's first-seen time and owner, leaving an existing row untouched."""
    existing: MissionThreadRow | None = await session.get(MissionThreadRow, thread_id)
    if existing is not None:
        return
    session.add(
        MissionThreadRow(
            thread_id=thread_id,
            created_at=datetime.now(UTC),
            operator_key_id=operator_key_id,
        )
    )
    await session.commit()


async def thread_owner(session: AsyncSession, thread_id: str) -> tuple[bool, str | None]:
    """Return ``(known, operator_key_id)`` for a thread or a replan child of one.

    A replan child (``<parent>:<n>``) has no row of its own and belongs to its
    parent's operator.
    """
    row: MissionThreadRow | None = await session.get(MissionThreadRow, thread_id)
    if row is None and ":" in thread_id:
        row = await session.get(MissionThreadRow, thread_id.rpartition(":")[0])
    return (row is not None, row.operator_key_id if row is not None else None)


async def lock_thread_for_update(
    session: AsyncSession,
    thread_id: str,
) -> MissionThreadRow | None:
    """Take an exclusive row lock on a thread, or return None if unknown.

    This is the per-thread mutex that stops two workers resuming the same
    interrupt. It is deliberately scoped to one row: it blocks a duplicate
    acknowledgement of *this* mission and nothing else, so holding it across the
    resume -- including the model call the resume triggers -- serialises only the
    request that must be serialised. The model client's own timeout bounds how
    long it can be held.

    On SQLite ``FOR UPDATE`` is a no-op and SQLite's database-level write lock
    does the serialising instead. The guarantee holds on both; only the mechanism
    differs.
    """
    result = await session.execute(
        select(MissionThreadRow).where(MissionThreadRow.thread_id == thread_id).with_for_update()
    )
    return result.scalars().first()


async def record_acknowledgement(
    session: AsyncSession,
    *,
    thread_id: str,
    actor: str,
    action: str,
    inputs_hash: str,
    calculator_version: str,
) -> None:
    """Record who acknowledged a thread's assessment, and which one.

    Raises KeyError when the thread is unknown: an acknowledgement with nothing
    to attach to is a bug in the caller, not a row to invent.
    """
    row: MissionThreadRow | None = await session.get(MissionThreadRow, thread_id)
    if row is None:
        raise KeyError(thread_id)
    row.ack_at = datetime.now(UTC)
    row.ack_actor = actor
    row.ack_action = action
    row.ack_inputs_hash = inputs_hash
    row.ack_calculator_version = calculator_version
    await session.commit()


async def _has_own_row(session: AsyncSession, thread_id: str) -> bool:
    """Return whether this id was planned as a thread, not handed out as a child."""
    return await session.get(MissionThreadRow, thread_id) is not None


async def next_replan_thread_id(session: AsyncSession, parent_thread_id: str) -> str:
    """Reserve and return the next child thread id for a replan.

    The counter lives on the parent row and is incremented as the id is handed
    out, so two concurrent replans of the same mission cannot be given the same
    child thread and overwrite one another's history.

    Raises:
        KeyError: when the parent thread is unknown.
    """
    row: MissionThreadRow | None = await session.get(MissionThreadRow, parent_thread_id)
    if row is None:
        raise KeyError(parent_thread_id)
    row.replan_count += 1
    # Skip an id a client planned as a thread of its own before new ids were
    # refused a ':'; a replan landing there would write into that thread.
    while await _has_own_row(session, f"{parent_thread_id}:{row.replan_count}"):
        row.replan_count += 1
    await session.commit()
    return f"{parent_thread_id}:{row.replan_count}"


async def get_acknowledgement(session: AsyncSession, thread_id: str) -> MissionThreadRow | None:
    """Return the thread row carrying its acknowledgement, or None if unknown."""
    return await session.get(MissionThreadRow, thread_id)


async def _expired_thread_ids(session: AsyncSession, cutoff: datetime) -> list[str]:
    """Return ids of threads first seen before the cutoff."""
    result = await session.execute(
        select(MissionThreadRow.thread_id)
        .where(MissionThreadRow.created_at < cutoff)
        .limit(_MAX_THREADS_PER_PURGE)
    )
    return list(result.scalars().all())


def _thread_family(thread_id: str, replan_count: int) -> list[str]:
    """Return a thread and the replan children it handed out (``<id>:1`` onward)."""
    return [thread_id, *(f"{thread_id}:{n}" for n in range(1, replan_count + 1))]


async def _purge_thread(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    thread_id: str,
) -> bool:
    """Purge one thread and its replan children; return whether this call did.

    Deleting the tracking row claims the thread: another worker's delete waits
    on the row lock, then finds nothing and skips it, so each thread is purged
    once however many workers run the pass. The row delete commits only after
    every checkpoint delete succeeds; a failure rolls it back so the next pass
    retries instead of orphaning a checkpoint.
    """
    async with session_factory() as session, session.begin():
        claimed = await session.execute(
            delete(MissionThreadRow)
            .where(MissionThreadRow.thread_id == thread_id)
            .returning(MissionThreadRow.replan_count)
        )
        replan_count: int | None = claimed.scalar_one_or_none()
        if replan_count is None:
            return False
        for member in _thread_family(thread_id, replan_count):
            # A child id with a row of its own is someone's thread, not a replan.
            if member == thread_id or not await _has_own_row(session, member):
                await checkpointer.adelete_thread(member)
    return True


async def purge_expired_threads(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    retention_days: float,
) -> int:
    """Delete checkpoints for threads older than the retention window.

    Returns the number of threads this call purged. A non-positive
    ``retention_days`` disables retention and purges nothing. Safe to run in
    several workers at once; see ``_purge_thread``.
    """
    if retention_days <= 0.0:
        return 0
    cutoff: datetime = datetime.now(UTC) - timedelta(days=retention_days)
    async with session_factory() as session:
        thread_ids: list[str] = await _expired_thread_ids(session, cutoff)
    if not thread_ids:
        return 0

    purged = 0
    for thread_id in thread_ids:
        try:
            purged += await _purge_thread(session_factory, checkpointer, thread_id)
        except Exception as exc:  # Retention must never take the app down.
            logger.error("Failed to delete checkpoint for thread %s: %s", thread_id, exc)
    logger.info("Purged %d expired mission threads (cutoff %s)", purged, cutoff.isoformat())
    return purged
