"""Reference-data seeding.

Loads the bundled aircraft and payload JSON files using a package-relative path
so seeding works regardless of the process working directory.
"""

import json
import logging
from pathlib import Path
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from suas.db.models import AircraftRow, PayloadRow
from suas.errors import SeedDataError

logger: Final[logging.Logger] = logging.getLogger(__name__)
_DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "data"


def _load_records(filename: str) -> list[dict[str, Any]]:
    """Return the value records from a bundled JSON reference file."""
    path: Path = _DATA_DIR / filename
    try:
        raw: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Failed to read seed file %s: %s", path, exc)
        raise SeedDataError(f"Cannot load seed file {filename}") from exc
    return list(raw.values())


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
    aircraft_records: list[dict[str, Any]] = _load_records("aircraft.json")
    payload_records: list[dict[str, Any]] = _load_records("payloads.json")
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
