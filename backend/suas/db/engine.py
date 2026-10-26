"""Async database engine and session factory helpers."""

from sqlalchemy import inspect
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


class SchemaNotMigratedError(RuntimeError):
    """The database has never been migrated and this process may not build it."""


async def prepare_schema(engine: AsyncEngine, *, alembic_owns_schema: bool) -> None:
    """Build the schema locally, or insist the deploy's migrate step already has.

    Where alembic owns the schema (``SUAS_REQUIRE_POSTGRES``, as the image
    sets), create_all must not run: on a fresh database a backend that started
    before the migrate step would create the tables with no version row, and the
    migration that creates them would then fail. A database stamped at another
    revision still starts, and ``/ready`` reports it ``pending``.

    Args:
        engine: The application's engine.
        alembic_owns_schema: Refuse an unmigrated database instead of building it.
    """
    if not alembic_owns_schema:
        await create_schema(engine)
        return
    async with engine.connect() as connection:
        migrated = await connection.run_sync(
            lambda sync: inspect(sync).has_table("alembic_version")
        )
    if not migrated:
        raise SchemaNotMigratedError(
            "The database has no alembic_version table. Run the migrate step "
            "(docker-entrypoint.sh migrate, or alembic upgrade head) before the "
            "server starts; with SUAS_REQUIRE_POSTGRES set the app does not "
            "create the schema itself."
        )
