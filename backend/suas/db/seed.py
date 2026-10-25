"""Reference-data seeding.

Loads the bundled aircraft and payload JSON files using a package-relative path
so seeding works regardless of the process working directory.
"""

import logging
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suas.db.models import AircraftRow, PayloadRow
from suas.reference_data import AIRCRAFT_FILE, PAYLOAD_FILE, load_rows

logger: Final[logging.Logger] = logging.getLogger(__name__)

# Any fixed bigint; it only has to be the same in every process that seeds.
SEED_LOCK_KEY: Final[int] = 0x5_5A5_5EED


async def _serialise_seeding(session: AsyncSession) -> None:
    """Hold a Postgres advisory lock until this seed's transaction ends.

    Each uvicorn worker seeds at startup. merge() is SELECT then INSERT, so on
    an empty database concurrent workers all INSERT the same rows and all but
    one fail on the primary key, which kills that worker and the container.
    With the lock they run one after another, and the later ones find the rows
    and update them. SQLite already serialises writers and has no such lock.
    """
    connection = await session.connection()
    if connection.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEED_LOCK_KEY})


async def seed_reference_data(session: AsyncSession) -> None:
    """Insert or update the bundled aircraft and payload rows (idempotent).

    The bundled JSON is the source of truth: every boot reconciles the stored
    rows against it, so corrected performance figures actually reach an existing
    database. A previous revision inserted only when the table was empty, which
    meant a data fix never propagated past the first deployment.

    Rows are matched by primary key and updated in place. Rows present in the
    database but absent from the JSON are left alone, so an operator can add
    their own airframes without them being deleted on restart.
    """
    aircraft_records: list[dict[str, Any]] = load_rows(AIRCRAFT_FILE)
    payload_records: list[dict[str, Any]] = load_rows(PAYLOAD_FILE)
    await _serialise_seeding(session)
    for record in aircraft_records:
        await session.merge(AircraftRow(**record))
    for record in payload_records:
        await session.merge(PayloadRow(**record))
    await session.commit()
    logger.info(
        "Reconciled reference data: %d aircraft, %d payloads",
        len(aircraft_records),
        len(payload_records),
    )
