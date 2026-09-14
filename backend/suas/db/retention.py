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


async def record_thread(session: AsyncSession, thread_id: str) -> None:
    """Record a thread's first-seen time, leaving an existing row untouched."""
    existing: MissionThreadRow | None = await session.get(MissionThreadRow, thread_id)
    if existing is not None:
        return
    session.add(MissionThreadRow(thread_id=thread_id, created_at=datetime.now(UTC)))
    await session.commit()


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


async def purge_expired_threads(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[Any],
    retention_days: float,
) -> int:
    """Delete checkpoints for threads older than the retention window.

    Returns the number of threads purged. A non-positive ``retention_days``
    disables retention and purges nothing.

    A thread whose checkpoint delete fails keeps its tracking row, so the next
    pass retries it rather than orphaning the checkpoint.
    """
    if retention_days <= 0.0:
        return 0
    cutoff: datetime = datetime.now(UTC) - timedelta(days=retention_days)
    async with session_factory() as session:
        thread_ids: list[str] = await _expired_thread_ids(session, cutoff)
    if not thread_ids:
        return 0

    purged: list[str] = []
    for thread_id in thread_ids:
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception as exc:  # Retention must never take the app down.
            logger.error("Failed to delete checkpoint for thread %s: %s", thread_id, exc)
            continue
        purged.append(thread_id)

    if purged:
        async with session_factory() as session:
            await session.execute(
                delete(MissionThreadRow).where(MissionThreadRow.thread_id.in_(purged))
            )
            await session.commit()
    logger.info("Purged %d expired mission threads (cutoff %s)", len(purged), cutoff.isoformat())
    return len(purged)
