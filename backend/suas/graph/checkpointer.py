"""Checkpointer construction.

Persistent checkpointing uses ``AsyncPostgresSaver`` backed by a connection
pool, matching the official LangGraph guidance for multi-instance async
deployments. When running against SQLite or in tests, an in-memory saver is
used instead.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from suas.config import Settings
from suas.db.startup_lock import startup_lock_session

logger: Final[logging.Logger] = logging.getLogger(__name__)


def _to_psycopg_conninfo(database_url: str) -> str:
    """Convert a SQLAlchemy Postgres URL to a plain psycopg conninfo string."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


async def _setup_schema(conninfo: str) -> None:
    """Apply the checkpoint migrations, one worker at a time.

    setup() reads the recorded version, then applies and records each newer
    migration, so workers starting together on an empty database all insert
    the same versions and the losers fail startup on checkpoint_migrations_pkey
    (main CI run 40240790618). Under the startup lock the later workers find
    the migrations recorded and apply nothing. It runs on its own autocommit
    connection because some migrations use CREATE INDEX CONCURRENTLY.
    """
    async with (
        await AsyncConnection.connect(conninfo, autocommit=True, row_factory=dict_row) as conn,
        startup_lock_session(conn) as locked,
    ):
        await AsyncPostgresSaver(locked).setup()


@asynccontextmanager
async def build_checkpointer(settings: Settings) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    """Yield a checkpointer appropriate for the configured database.

    For PostgreSQL this runs the checkpoint schema setup under the startup
    lock, opens a connection pool, and closes the pool on exit. For any other backend it yields an
    in-memory saver.
    """
    if not settings.uses_postgres:
        logger.info("Using in-memory checkpointer")
        yield InMemorySaver()
        return

    conninfo: str = _to_psycopg_conninfo(settings.database_url)
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        open=False,
        max_size=settings.pool_max_size,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    try:
        await _setup_schema(conninfo)
        saver = AsyncPostgresSaver(pool)
        logger.info("Using Postgres checkpointer")
        yield saver
    finally:
        await pool.close()
