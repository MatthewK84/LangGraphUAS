"""Postgres advisory locks that serialise startup writes across workers.

The container runs several uvicorn workers, and each runs the whole lifespan
against the same database. Every startup write is check-then-write --
``create_all`` inspects then creates, the seed merges (SELECT then INSERT), and
the checkpointer's ``setup()`` reads its migration version then applies and
records the rest -- so on an empty database concurrent workers all take the
"missing" branch and all but one fail on a unique key, which fails that
worker's startup and stops the container. Under these locks the workers run
those steps one after another, and the later ones find the work done.

SQLite already serialises writers and has no advisory locks, so on SQLite
both helpers do nothing.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from psycopg import AsyncConnection
from psycopg.rows import DictRow
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection as SqlAlchemyConnection

# Any fixed bigints; each only has to be the same in every process that starts.
# Two keys, not one: a worker blocked on the transactional lock holds a
# snapshot, so it must never wait on the checkpointer-setup holder, whose
# CREATE INDEX CONCURRENTLY waits for every older snapshot.
STARTUP_LOCK_KEY: Final[int] = 0x5_5A5_5EED
CHECKPOINT_SETUP_LOCK_KEY: Final[int] = 0x5_5A5_5EEE
_POLL_INTERVAL_S: Final[float] = 0.1


async def hold_startup_lock(connection: SqlAlchemyConnection) -> None:
    """Hold the startup lock until this connection's transaction ends."""
    if connection.dialect.name == "postgresql":
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": STARTUP_LOCK_KEY}
        )


async def _try_startup_lock(connection: AsyncConnection[DictRow]) -> bool:
    """Take the session-scoped checkpoint-setup lock if it is free; never wait."""
    cursor = await connection.execute(
        "SELECT pg_try_advisory_lock(%s) AS locked", (CHECKPOINT_SETUP_LOCK_KEY,)
    )
    row: DictRow | None = await cursor.fetchone()
    return row is not None and bool(row["locked"])


@asynccontextmanager
async def startup_lock_session(
    connection: AsyncConnection[DictRow],
) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Hold the checkpoint-setup lock on an autocommit psycopg connection.

    For work that cannot run inside one transaction, such as the checkpointer
    migrations' ``CREATE INDEX CONCURRENTLY``. The lock is session-scoped, so
    it is released explicitly, and by Postgres if the connection dies.

    Waiters poll rather than block in ``pg_advisory_lock``: a session blocked
    in that statement holds a snapshot, CREATE INDEX CONCURRENTLY in the lock
    holder waits for every older snapshot to finish, and Postgres reports the
    pair as a deadlock. Between polls a waiter is idle and holds nothing.
    """
    while not await _try_startup_lock(connection):
        await asyncio.sleep(_POLL_INTERVAL_S)
    try:
        yield connection
    finally:
        await connection.execute("SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK_KEY,))
