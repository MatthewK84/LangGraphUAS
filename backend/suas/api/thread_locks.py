"""Per-thread mutexes for resuming an interrupt.

Two layers, because one is not enough on its own.

``FOR UPDATE`` on the mission row serialises workers that share a Postgres
database, which is the production shape. It does nothing on SQLite, where the
clause is silently ignored, and nothing between two coroutines inside one
process that share a connection pool.

This module covers that second case: an ``asyncio.Lock`` per thread id, held
across the same critical section. Together they mean the guarantee -- one
interrupt is resumed once -- does not depend on which database happens to be
configured.
"""

import asyncio
from typing import Final

# Bounded so a long-running process cannot accumulate a lock per thread it has
# ever seen. Locks above this count are dropped once they are free; dropping a
# free lock is safe, because the next caller simply makes a new one.
_MAX_TRACKED: Final[int] = 4096

_locks: Final[dict[str, asyncio.Lock]] = {}


def _lock_for(thread_id: str) -> asyncio.Lock:
    """Return the lock for a thread, creating it if this is the first caller."""
    existing = _locks.get(thread_id)
    if existing is not None:
        return existing
    created = asyncio.Lock()
    _locks[thread_id] = created
    return created


def _release(thread_id: str) -> None:
    """Drop a free lock once the table has grown past its bound."""
    if len(_locks) <= _MAX_TRACKED:
        return
    lock = _locks.get(thread_id)
    if lock is not None and not lock.locked():
        _locks.pop(thread_id, None)


class thread_lock:  # noqa: N801 - reads as a context manager at the call site
    """Async context manager holding this process's lock for one thread."""

    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id
        self._lock = _lock_for(thread_id)

    async def __aenter__(self) -> "thread_lock":
        """Acquire the lock."""
        await self._lock.acquire()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Release the lock and prune if the table has grown."""
        self._lock.release()
        _release(self._thread_id)
