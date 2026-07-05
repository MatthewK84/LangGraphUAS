"""Data access functions.

Repository functions return frozen domain models (``Aircraft`` / ``Payload``)
rather than leaking ORM rows into the rest of the application (Principle 2/8).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suas.db.models import AircraftRow, PayloadRow
from suas.schemas.domain import Aircraft, Payload


async def get_aircraft(session: AsyncSession, aircraft_id: str) -> Aircraft | None:
    """Return the aircraft with the given id, or None if absent."""
    row: AircraftRow | None = await session.get(AircraftRow, aircraft_id)
    if row is None:
        return None
    return Aircraft.model_validate(row, from_attributes=True)


async def get_payload(session: AsyncSession, payload_id: str) -> Payload | None:
    """Return the payload with the given id, or None if absent."""
    row: PayloadRow | None = await session.get(PayloadRow, payload_id)
    if row is None:
        return None
    return Payload.model_validate(row, from_attributes=True)


async def count_aircraft(session: AsyncSession) -> int:
    """Return the number of aircraft rows currently stored."""
    result = await session.execute(select(AircraftRow.id))
    return len(result.scalars().all())
