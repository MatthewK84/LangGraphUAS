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
from suas.db.repository import count_aircraft
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
    """Populate aircraft and payload tables if they are empty (idempotent)."""
    existing: int = await count_aircraft(session)
    if existing > 0:
        logger.info("Reference data already present (%d aircraft); skipping seed", existing)
        return
    for record in _load_records("aircraft.json"):
        session.add(AircraftRow(**record))
    for record in _load_records("payloads.json"):
        session.add(PayloadRow(**record))
    await session.commit()
    logger.info("Seeded reference aircraft and payload data")
