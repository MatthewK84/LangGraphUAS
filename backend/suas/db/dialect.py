"""The ``INSERT`` construct that can say ``ON CONFLICT`` for the bound database."""

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


def upsert_insert(
    session: AsyncSession, table: type[DeclarativeBase]
) -> postgresql.Insert | sqlite.Insert:
    """Return an insert for ``table`` with the dialect's ``on_conflict_*`` methods."""
    if session.bind.dialect.name == "postgresql":
        return postgresql.insert(table)
    return sqlite.insert(table)
