"""Async database engine and session factory helpers."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from suas.db.models import Base
from suas.db.startup_lock import hold_startup_lock


def create_engine(database_url: str) -> AsyncEngine:
    """Return a configured async SQLAlchemy engine.

    Args:
        database_url: An async SQLAlchemy URL, e.g. ``postgresql+psycopg://...``
            or ``sqlite+aiosqlite:///./local.db``.
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine: AsyncEngine) -> None:
    """Create all tables if they do not already exist.

    Serialised across workers: create_all inspects then creates, so two
    workers on an empty Postgres database collide on the table's type name.
    """
    async with engine.begin() as connection:
        await hold_startup_lock(connection)
        await connection.run_sync(Base.metadata.create_all)
