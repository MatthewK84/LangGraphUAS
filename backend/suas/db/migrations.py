"""What the readiness probe knows about the database schema version.

``alembic upgrade head`` runs before the server starts (docker-entrypoint.sh),
so a deployed database whose ``alembic_version`` row is not
:data:`EXPECTED_REVISION` is running code ahead of its schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_REVISION: Final[str] = "0014"
"""The alembic head this code needs. A test pins it to the migration scripts."""


class MigrationState(StrEnum):
    """Readiness verdict on the schema version."""

    OK = "ok"
    PENDING = "pending"
    NOT_TRACKED = "not_tracked"


async def migration_state(session: AsyncSession, *, tracked_required: bool) -> MigrationState:
    """Compare the stamped alembic revision with :data:`EXPECTED_REVISION`.

    With no ``alembic_version`` table the schema came from ``create_all``. That
    is the normal local SQLite path (``NOT_TRACKED``) but never a migrated
    deployment, so it is ``PENDING`` when ``tracked_required``.
    """
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
    except (OperationalError, ProgrammingError):
        await session.rollback()
        return MigrationState.PENDING if tracked_required else MigrationState.NOT_TRACKED
    stamped = {row[0] for row in result}
    return MigrationState.OK if stamped == {EXPECTED_REVISION} else MigrationState.PENDING
